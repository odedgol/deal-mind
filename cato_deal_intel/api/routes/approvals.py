from fastapi import APIRouter, HTTPException

from .. import dependencies as deps
from ..schemas import ApprovalDecisionRequest, ApprovalInboxCount, ApprovalInboxItem

router = APIRouter(tags=["Runs"])


@router.get(
    "/approvals/inbox",
    response_model=list[ApprovalInboxItem],
    summary="List pending Deal Desk approvals",
)
def approval_inbox(user_id: str) -> list[ApprovalInboxItem]:
    """Return pending requests assigned to this demo Deal Desk Approver."""
    if not deps.is_deal_desk_approver(deps.permission_profile(user_id)):
        return []
    return [
        ApprovalInboxItem(approval_request=request, brief=brief)
        for request, brief in deps.APPROVAL_STORE.inbox(user_id)
    ]


@router.get(
    "/approvals/inbox/count",
    response_model=ApprovalInboxCount,
    summary="Get the pending approval count for a reviewer",
)
def approval_inbox_count(user_id: str) -> ApprovalInboxCount:
    """Return a badge count without exposing pending requests or deal details."""
    if not deps.is_deal_desk_approver(deps.permission_profile(user_id)):
        return ApprovalInboxCount(count=0)
    return ApprovalInboxCount(
        count=len(deps.APPROVAL_STORE.inbox(user_id))
    )


@router.post(
    "/approvals/{run_id}/decision",
    response_model=ApprovalInboxItem,
    summary="Approve or reject a pending run",
)
def decide_approval(run_id: str, request: ApprovalDecisionRequest) -> ApprovalInboxItem:
    """Update the existing run; the brief generation and agents are not rerun."""
    if not deps.is_deal_desk_approver(deps.permission_profile(request.reviewer_user_id)):
        raise HTTPException(
            status_code=403,
            detail="Only a Deal Desk Approver can decide this request.",
        )
    with deps.BRIEF_LOCK:
        try:
            approval_request, brief = deps.APPROVAL_STORE.decide(
                run_id,
                reviewer_user_id=request.reviewer_user_id,
                decision=request.decision,
                comment=request.comment,
            )
        except FileNotFoundError as error:
            raise HTTPException(
                status_code=404, detail="Pending approval request was not found."
            ) from error
        except PermissionError as error:
            raise HTTPException(
                status_code=403, detail="This user cannot decide this request."
            ) from error
        except ValueError as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
    return ApprovalInboxItem(approval_request=approval_request, brief=brief)
