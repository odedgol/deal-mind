from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException

from ...llm.settings import configured_llm
from ...models import ApprovalRequest, Brief, DeniedResult
from ...orchestration.workflow import create_brief
from ...retrieval.embeddings import configured_embedding_provider
from .. import dependencies as deps
from ..schemas import BriefRequest

router = APIRouter(tags=["Demo"])


@router.post(
    "/brief",
    response_model=Brief | DeniedResult,
    summary="Generate a deal brief",
    description=(
        "Runs authorization before evidence retrieval. Authorized requests return the complete "
        "brief; unauthorized requests return a generic denial without restricted deal details. "
        "For `OPP-1003`, try both the authorized demo user `USR-5003` and unauthorized user "
        "`USR-5007`."
    ),
)
def generate_brief(request: BriefRequest) -> Brief | DeniedResult:
    """Run the same workflow exposed by the CLI and return its result."""
    with deps.BRIEF_LOCK:
        if deps.requester_is_only_eligible_approver(
            request.opportunity_id, request.user_id
        ):
            raise HTTPException(
                status_code=409,
                detail="This approval-required request needs another Deal Desk Approver.",
            )
        result = create_brief(
            root=deps.DATA_ROOT,
            source=deps.SOURCE,
            artifacts_root=deps.ARTIFACT_ROOT,
            opportunity_id=request.opportunity_id,
            user_id=request.user_id,
            llm=configured_llm(),
            approval_decision="pending",
            qdrant_path=deps.DEFAULT_QDRANT_PATH,
            qdrant_client_factory=deps.QDRANT_CLIENTS,
            embedding_provider=configured_embedding_provider(),
        )
        if isinstance(result, Brief) and result.run_status == "awaiting_approval":
            approval_request = _new_approval_request(result, request.user_id)
            if not approval_request.eligible_approver_user_ids:
                raise HTTPException(
                    status_code=409,
                    detail="No eligible Deal Desk Approver is configured for this run.",
                )
            deps.APPROVAL_STORE.create(approval_request)
        return result


def _new_approval_request(brief: Brief, requester_user_id: str) -> ApprovalRequest:
    profiles = deps.SOURCE.permissions()
    requester = deps.SOURCE.permission_profile(requester_user_id)
    opportunity = deps.SOURCE.opportunity(brief.opportunity_id)
    approvers = deps.eligible_approvers(opportunity, profiles, requester_user_id)
    return ApprovalRequest(
        run_id=brief.run_id,
        opportunity_id=brief.opportunity_id,
        requester_user_id=requester_user_id,
        requester_name=requester.user_name if requester else "Unknown requester",
        eligible_approver_user_ids=approvers,
        requested_actions=[
            action.action for action in brief.recommended_next_actions if action.requires_approval
        ],
        requested_at=datetime.now(UTC),
    )
