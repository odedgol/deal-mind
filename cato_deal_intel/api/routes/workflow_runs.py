import json
from pathlib import Path

from fastapi import APIRouter, HTTPException

from ...models import Brief, CostSummary
from .. import dependencies as deps

router = APIRouter(tags=["Runs"])


@router.get(
    "/runs/requests",
    response_model=list[Brief],
    summary="Restore this requester's approval-routed briefs",
)
def requester_runs(user_id: str) -> list[Brief]:
    """Let a requester return to their run and see its latest approval status."""
    return deps.APPROVAL_STORE.requester_runs(user_id)


@router.get(
    "/runs/{run_id}/usage",
    response_model=CostSummary,
    summary="Get model usage for a run",
    description="Returns token and cost totals saved with a completed run.",
    responses={404: {"description": "No completed run exists with this ID."}},
)
def get_run_usage(run_id: str) -> CostSummary:
    """Return the persisted model usage summary for one completed run."""
    path = Path(deps.ARTIFACT_ROOT) / run_id / "brief.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run was not found.")
    brief = Brief.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return brief.cost_summary
