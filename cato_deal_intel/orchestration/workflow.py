import uuid
from collections.abc import Callable
from typing import Literal, cast

from ..llm.protocols import LLMProvider
from ..models import RecommendedAction, WorkflowResult
from ..observability.tracing import AgentTraceCollector
from ..repositories.contracts import DealRepository, EvidenceRepository
from .graph import InitialDealState, build_deal_graph
from .services import RunArtifactService

DEAL_GRAPH = build_deal_graph()


def create_brief(
    *,
    deal_repository: DealRepository,
    opportunity_id: str,
    user_id: str,
    llm: LLMProvider,
    run_artifact_service: RunArtifactService,
    evidence_repository: EvidenceRepository,
    approval_decision: Literal["ask", "approved", "rejected", "pending"] = "pending",
    approval_prompt: (
        Callable[[list[RecommendedAction]], Literal["approved", "rejected"]] | None
    ) = None,
) -> WorkflowResult:
    """Run the LangGraph flow and return either a brief or a safe denial."""
    initial_state: InitialDealState = {
        "deal_repository": deal_repository,
        "evidence_repository": evidence_repository,
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
