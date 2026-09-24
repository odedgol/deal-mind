from pathlib import Path
from typing import Annotated, Any, Literal, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from .agents import (
    AgentContext,
    ConversationIntelligenceAgent,
    DealContextAgent,
    NegotiationStrategyAgent,
    StakeholderMapAgent,
)
from .artifact_store import ArtifactStore
from .data import SourceData
from .llm import LLMAdapter
from .models import (
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
    StrategyOutput,
)
from .retrieval import EvidenceRetriever
from .services import ApprovalService, DealService, EvidenceService, build_brief
from .tools import (
    ApprovalRequestTool,
    AuthorizedEvidenceSearchTool,
    DealContextTool,
    DealDeskPolicyTool,
    RecommendationValidationTool,
)


def _merge_unique_evidence(
    current: list[EvidenceItem], incoming: list[EvidenceItem]
) -> list[EvidenceItem]:
    merged = {item.evidence_id: item for item in current}
    merged.update({item.evidence_id: item for item in incoming})
    return list(merged.values())


class DealState(TypedDict, total=False):
    root: Path
    artifacts_root: Path
    opportunity_id: str
    user_id: str
    llm: LLMAdapter
    approval_decision: Literal["approved", "rejected", "pending"]
    run_id: str
    opportunity: Opportunity
    authorization: AuthorizationDecision
    evidence: Annotated[list[EvidenceItem], _merge_unique_evidence]
    deal_snapshot: DealSnapshot
    conversation: AgentOutput
    stakeholders: AgentOutput
    strategy: StrategyOutput
    actions: list[RecommendedAction]
    approvals: list[ApprovalRecord]
    brief: Brief
    traces: list[AgentTrace]
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
    source = SourceData(state["root"])
    opportunity, decision = DealService(source).authorize(state["opportunity_id"], state["user_id"])
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
    source = SourceData(state["root"])
    service = EvidenceService(source, EvidenceRetriever())
    evidence = service.retrieve(state["opportunity_id"], state["authorization"])
    return {"evidence": evidence}


def deal_context_node(state: DealState) -> dict[str, object]:
    snapshot = DealContextAgent(DealContextTool(state["opportunity"])).run(
        AgentContext(state["opportunity"], state["evidence"])
    )
    return {"deal_snapshot": snapshot, "traces": []}


def conversation_node(state: DealState) -> dict[str, object]:
    service = EvidenceService(SourceData(state["root"]), EvidenceRetriever())
    search = AuthorizedEvidenceSearchTool(service, state["authorization"])
    output = ConversationIntelligenceAgent(state["llm"], search).run(
        AgentContext(state["opportunity"], state["evidence"])
    )
    return {
        "conversation": output,
        "evidence": _merge_evidence(state["evidence"], search.retrieved_evidence),
    }


def stakeholders_node(state: DealState) -> dict[str, object]:
    service = EvidenceService(SourceData(state["root"]), EvidenceRetriever())
    search = AuthorizedEvidenceSearchTool(service, state["authorization"])
    output = StakeholderMapAgent(state["llm"], search).run(
        AgentContext(state["opportunity"], state["evidence"])
    )
    return {
        "stakeholders": output,
        "evidence": _merge_evidence(state["evidence"], search.retrieved_evidence),
    }


def strategy_node(state: DealState) -> dict[str, object]:
    service = EvidenceService(SourceData(state["root"]), EvidenceRetriever())
    policy = DealDeskPolicyTool(service, state["authorization"])
    strategy_agent = NegotiationStrategyAgent(
        state["llm"],
        RecommendationValidationTool(),
        policy,
        ApprovalRequestTool(ApprovalService()),
    )
    context = AgentContext(state["opportunity"], state["evidence"])
    output = strategy_agent.run(context, [state["conversation"], state["stakeholders"]])
    evidence = _merge_evidence(state["evidence"], policy.retrieved_evidence)
    return {"strategy": output, "evidence": evidence}


def approval_node(state: DealState) -> dict[str, object]:
    actions, approvals = ApprovalService().prepare(
        state["opportunity"],
        state["strategy"].actions,
        state.get("approval_decision", "pending"),
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
    )
    return {"brief": brief}


def persist_node(state: DealState) -> dict[str, object]:
    ArtifactStore(state["artifacts_root"]).save_run(
        run_id=state["run_id"],
        opportunity=state["opportunity"],
        decision=state["authorization"],
        evidence=state["evidence"],
        conversation=state["conversation"],
        stakeholders=state["stakeholders"],
        strategy=state["strategy"],
        approvals=state["approvals"],
        brief=state["brief"],
        traces=state.get("traces", []),
    )
    return {}


def _merge_evidence(
    primary: list[EvidenceItem], additional: list[EvidenceItem]
) -> list[EvidenceItem]:
    merged = {item.evidence_id: item for item in primary}
    merged.update({item.evidence_id: item for item in additional})
    return list(merged.values())
