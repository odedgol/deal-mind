from collections.abc import Callable
from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from qdrant_client import QdrantClient

from ..agents.core import (
    AgentContext,
    ConversationIntelligenceAgent,
    DealContextAgent,
    NegotiationStrategyAgent,
    StakeholderMapAgent,
)
from ..agents.tools import (
    ApprovalRequestTool,
    AuthorizedEvidenceSearchTool,
    DealContextTool,
    DealDeskPolicyTool,
    RecommendationValidationTool,
)
from ..llm.protocols import LLMProvider
from ..llm.settings import usage_summary
from ..models import (
    AgentOutput,
    AgentTrace,
    ApprovalRecord,
    AuthorizationDecision,
    Brief,
    DealSnapshot,
    DeniedResult,
    EvidenceItem,
    Opportunity,
    RecommendedAction,
    RetrievalDebug,
    StrategyOutput,
)
from ..observability.tracing import AgentTraceCollector, trace_operation
from ..repositories.contracts import DealRepository, EvidenceRepository
from ..retrieval.embeddings import EmbeddingProvider
from ..retrieval.index import EvidenceRetriever
from ..storage.artifact_store import ArtifactStore
from .services import ApprovalService, DealService, EvidenceService, build_brief


def _merge_unique_evidence(
    current: list[EvidenceItem], incoming: list[EvidenceItem]
) -> list[EvidenceItem]:
    merged = {item.evidence_id: item for item in current}
    merged.update({item.evidence_id: item for item in incoming})
    return list(merged.values())


def _merge_traces(current: list[AgentTrace], incoming: list[AgentTrace]) -> list[AgentTrace]:
    traces = {trace.trace_id: trace for trace in current}
    traces.update({trace.trace_id: trace for trace in incoming})
    return list(traces.values())


def _merge_retrieval_debug(
    current: list[RetrievalDebug], incoming: list[RetrievalDebug]
) -> list[RetrievalDebug]:
    return current + incoming


class DealState(TypedDict, total=False):
    root: Path
    source: DealRepository
    artifacts_root: Path
    opportunity_id: str
    user_id: str
    llm: LLMProvider
    approval_decision: Literal["ask", "approved", "rejected", "pending"]
    approval_prompt: Callable[[list[RecommendedAction]], Literal["approved", "rejected"]]
    run_id: str
    qdrant_path: Path
    qdrant_client: QdrantClient
    qdrant_client_factory: Callable[[], QdrantClient]
    embedding_provider: EmbeddingProvider
    opportunity: Opportunity
    authorization: AuthorizationDecision
    evidence: Annotated[list[EvidenceItem], _merge_unique_evidence]
    retrieval_debug: Annotated[list[RetrievalDebug], _merge_retrieval_debug]
    retriever: EvidenceRepository
    deal_snapshot: DealSnapshot
    conversation: AgentOutput
    stakeholders: AgentOutput
    strategy: StrategyOutput
    actions: list[RecommendedAction]
    approvals: list[ApprovalRecord]
    brief: Brief
    traces: Annotated[list[AgentTrace], _merge_traces]
    trace_collector: AgentTraceCollector
    denial: DeniedResult


def build_deal_graph() -> CompiledStateGraph[Any, Any, Any, Any]:
    graph = StateGraph(DealState)
    graph.add_node("authorize", authorize_node)
    graph.add_node("safe_denial", safe_denial_node)
    graph.add_node("retrieve", retrieve_node)
    graph.add_node("deal_context", deal_context_node)
    graph.add_node("conversation", conversation_node)
    graph.add_node("stakeholders", stakeholders_node)
    graph.add_node("strategy", strategy_node)
    graph.add_node("approval", approval_node)
    graph.add_node("build_brief", build_brief_node)
    graph.add_node("persist", persist_node)

    graph.add_edge(START, "authorize")
    graph.add_conditional_edges(
        "authorize",
        route_after_authorization,
        {"authorized": "retrieve", "denied": "safe_denial"},
    )
    graph.add_edge("retrieve", "deal_context")
    graph.add_edge("deal_context", "conversation")
    graph.add_edge("deal_context", "stakeholders")
    graph.add_edge(["conversation", "stakeholders"], "strategy")
    graph.add_edge("strategy", "approval")
    graph.add_edge("approval", "build_brief")
    graph.add_edge("build_brief", "persist")
    graph.add_edge("persist", END)
    graph.add_edge("safe_denial", END)
    return graph.compile()


def authorize_node(state: DealState) -> dict[str, object]:
    opportunity, decision = DealService(state["source"]).authorize(
        state["opportunity_id"], state["user_id"]
    )
    authorized_state = {"opportunity": opportunity} if decision.allowed else {}
    return {**authorized_state, "authorization": decision}


def route_after_authorization(state: DealState) -> Literal["authorized", "denied"]:
    """Choose the next graph branch from the authorization decision."""
    return "authorized" if state["authorization"].allowed else "denied"


def safe_denial_node(state: DealState) -> dict[str, object]:
    """Return a generic denial without exposing protected deal information."""
    denial = DeniedResult(
        run_id=state["run_id"],
        opportunity_id=state["opportunity_id"],
        user_id=state["user_id"],
        message="Requester is not authorized for this request.",
    )
    return {"denial": denial}


def retrieve_node(state: DealState) -> dict[str, object]:
    client = state.get("qdrant_client")
    if client is None:
        factory = state.get("qdrant_client_factory")
        client = factory() if factory is not None else None
    retriever = EvidenceRetriever(
        client=client,
        path=state["qdrant_path"],
        require_existing=True,
        embedding_provider=state["embedding_provider"],
    )
    service = EvidenceService(
        state["source"], retriever, state["trace_collector"], state["run_id"], []
    )
    evidence = service.retrieve(state["opportunity_id"], state["authorization"])
    return {
        "evidence": evidence,
        "retriever": retriever,
        "retrieval_debug": service.retrieval_debug,
    }


def deal_context_node(state: DealState) -> dict[str, object]:
    agent = DealContextAgent(
        DealContextTool(state["opportunity"], state["trace_collector"], state["run_id"])
    )
    snapshot, trace = _run_traced_agent(
        run_id=state["run_id"],
        agent_name=agent.name,
        collector=state["trace_collector"],
        operation=lambda: agent.run(AgentContext(state["opportunity"], state["evidence"])),
    )
    return {"deal_snapshot": snapshot, "traces": [trace]}


def conversation_node(state: DealState) -> dict[str, object]:
    service = EvidenceService(
        state["source"],
        state["retriever"],
        state["trace_collector"],
        state["run_id"],
        [],
    )
    search = AuthorizedEvidenceSearchTool(
        service, state["authorization"], state["trace_collector"], state["run_id"]
    )
    agent = ConversationIntelligenceAgent(state["llm"], search)
    output, trace = _run_traced_agent(
        run_id=state["run_id"],
        agent_name=agent.name,
        collector=state["trace_collector"],
        operation=lambda: agent.run(AgentContext(state["opportunity"], state["evidence"])),
    )
    return {
        "conversation": output,
        "evidence": _merge_evidence(state["evidence"], search.retrieved_evidence),
        "retrieval_debug": service.retrieval_debug,
        "traces": [trace],
    }


def stakeholders_node(state: DealState) -> dict[str, object]:
    service = EvidenceService(
        state["source"],
        state["retriever"],
        state["trace_collector"],
        state["run_id"],
        [],
    )
    search = AuthorizedEvidenceSearchTool(
        service, state["authorization"], state["trace_collector"], state["run_id"]
    )
    agent = StakeholderMapAgent(state["llm"], search)
    output, trace = _run_traced_agent(
        run_id=state["run_id"],
        agent_name=agent.name,
        collector=state["trace_collector"],
        operation=lambda: agent.run(AgentContext(state["opportunity"], state["evidence"])),
    )
    return {
        "stakeholders": output,
        "evidence": _merge_evidence(state["evidence"], search.retrieved_evidence),
        "retrieval_debug": service.retrieval_debug,
        "traces": [trace],
    }


def strategy_node(state: DealState) -> dict[str, object]:
    service = EvidenceService(
        state["source"],
        state["retriever"],
        state["trace_collector"],
        state["run_id"],
        [],
    )
    policy = DealDeskPolicyTool(
        service, state["authorization"], state["trace_collector"], state["run_id"]
    )
    strategy_agent = NegotiationStrategyAgent(
        state["llm"],
        RecommendationValidationTool(state["trace_collector"], state["run_id"]),
        policy,
        ApprovalRequestTool(ApprovalService(), state["trace_collector"], state["run_id"]),
    )
    context = AgentContext(state["opportunity"], state["evidence"])
    output, trace = _run_traced_agent(
        run_id=state["run_id"],
        agent_name=strategy_agent.name,
        collector=state["trace_collector"],
        operation=lambda: strategy_agent.run(
            context, [state["conversation"], state["stakeholders"]]
        ),
    )
    evidence = _merge_evidence(state["evidence"], policy.retrieved_evidence)
    _, recommendation_trace = trace_operation(
        collector=state["trace_collector"],
        run_id=state["run_id"],
        event_type="recommendation",
        name="strategy.recommendations",
        operation=lambda: None,
        metadata={"action_count": str(len(output.actions))},
    )
    return {
        "strategy": output,
        "evidence": evidence,
        "retrieval_debug": service.retrieval_debug,
        "traces": [trace, recommendation_trace],
    }


def approval_node(state: DealState) -> dict[str, object]:
    decision = state.get("approval_decision", "pending")
    if decision == "ask":
        prompt = state.get("approval_prompt")
        if prompt is None:
            raise ValueError("An approval prompt is required when approval_decision='ask'.")
        decision = prompt(state["strategy"].actions)
    (actions, approvals), _ = trace_operation(
        collector=state["trace_collector"],
        run_id=state["run_id"],
        event_type="approval",
        name="approval.prepare",
        operation=lambda: ApprovalService().prepare(
            state["opportunity"],
            state["strategy"].actions,
            decision,
        ),
        metadata={"action_count": str(len(state["strategy"].actions))},
    )
    return {"actions": actions, "approvals": approvals}


def build_brief_node(state: DealState) -> dict[str, object]:
    brief = build_brief(
        run_id=state["run_id"],
        opportunity=state["opportunity"],
        evidence=state["evidence"],
        deal_snapshot=state["deal_snapshot"],
        conversation=state["conversation"],
        stakeholders=state["stakeholders"],
        strategy=state["strategy"],
        actions=state["actions"],
        approvals=state["approvals"],
        retrieval_debug=state.get("retrieval_debug", []),
        cost_summary=usage_summary(state["llm"]),
    )
    return {"brief": brief}


def persist_node(state: DealState) -> dict[str, object]:
    ArtifactStore(state["artifacts_root"]).save_run(
        run_id=state["run_id"],
        requester_user_id=state["user_id"],
        opportunity=state["opportunity"],
        decision=state["authorization"],
        evidence=state["evidence"],
        conversation=state["conversation"],
        stakeholders=state["stakeholders"],
        strategy=state["strategy"],
        approvals=state["approvals"],
        brief=state["brief"],
        traces=state["trace_collector"].traces,
    )
    return {}


def _merge_evidence(
    primary: list[EvidenceItem], additional: list[EvidenceItem]
) -> list[EvidenceItem]:
    merged = {item.evidence_id: item for item in primary}
    merged.update({item.evidence_id: item for item in additional})
    return list(merged.values())


def _run_traced_agent[T](
    *,
    run_id: str,
    agent_name: str,
    collector: AgentTraceCollector,
    operation: Callable[[], T],
) -> tuple[T, AgentTrace]:
    return trace_operation(
        collector=collector,
        run_id=run_id,
        event_type="agent",
        name=agent_name,
        operation=operation,
    )
