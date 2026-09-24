import uuid
from pathlib import Path
from typing import Literal, cast

from .graph import DealState, build_deal_graph
from .llm import LLMAdapter
from .models import WorkflowResult


def create_brief(
    *,
    root: Path,
    artifacts_root: Path,
    opportunity_id: str,
    user_id: str,
    llm: LLMAdapter,
    approval_decision: Literal["approved", "rejected", "pending"] = "pending",
) -> WorkflowResult:
    """Run the LangGraph flow and return either a brief or a safe denial."""
    initial_state: DealState = {
        "root": root,
        "artifacts_root": artifacts_root,
        "opportunity_id": opportunity_id,
        "user_id": user_id,
        "llm": llm,
        "approval_decision": approval_decision,
        "run_id": uuid.uuid4().hex,
    }
    result = build_deal_graph().invoke(initial_state)
    return cast(WorkflowResult, result.get("brief") or result["denial"])
