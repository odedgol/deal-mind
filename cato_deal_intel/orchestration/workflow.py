import uuid
from collections.abc import Callable
from typing import Literal, cast

from ..llm.protocols import LLMProvider
from ..models import RecommendedAction, WorkflowResult
from ..observability.tracing import AgentTraceCollector
from .graph import InitialDealState, build_deal_graph
from .services import (
    ApprovalService,
    DealService,
    EvidenceServiceFactory,
    RunArtifactService,
)

DEAL_GRAPH = build_deal_graph()


def create_brief(
    *,
    deal_service: DealService,
    opportunity_id: str,
    user_id: str,
    llm: LLMProvider,
    run_artifact_service: RunArtifactService,
    evidence_service_factory: EvidenceServiceFactory,
    approval_decision: Literal["ask", "approved", "rejected", "pending"] = "pending",
    approval_prompt: (
        Callable[[list[RecommendedAction]], Literal["approved", "rejected"]] | None
    ) = None,
) -> WorkflowResult:
    """Run the LangGraph flow and return either a brief or a safe denial."""
    initial_state: InitialDealState = {
        "deal_service": deal_service,
        "evidence_service_factory": evidence_service_factory,
        "approval_service": ApprovalService(),
        "run_artifact_service": run_artifact_service,
        "opportunity_id": opportunity_id,
        "user_id": user_id,
        "llm": llm,
        "approval_decision": approval_decision,
        "run_id": uuid.uuid4().hex,
        "trace_collector": AgentTraceCollector(),
        "retrieval_debug": [],
    }
    if approval_prompt is not None:
        initial_state["approval_prompt"] = approval_prompt
    try:
        result = DEAL_GRAPH.invoke(initial_state)
    except Exception as error:
        traces = initial_state["trace_collector"].traces
        if traces:
            run_artifact_service.save_failed_run(
                run_id=initial_state["run_id"],
                opportunity_id=opportunity_id,
                user_id=user_id,
                traces=traces,
                error=error,
            )
        raise
    return cast(WorkflowResult, result.get("brief") or result["denial"])
