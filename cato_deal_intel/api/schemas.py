from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from ..models import ApprovalRequest, Brief


class BriefRequest(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {"opportunity_id": "OPP-1001", "user_id": "USR-5001"},
                {"opportunity_id": "OPP-1003", "user_id": "USR-5003"},
                {"opportunity_id": "OPP-1003", "user_id": "USR-5007"},
            ],
        },
    )

    opportunity_id: str = Field(description="Opportunity to prepare a deal brief for.")
    user_id: str = Field(
        description="Synthetic demo identity; this prototype does not authenticate it."
    )


class ApprovalDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reviewer_user_id: str = Field(description="Synthetic Deal Desk Approver demo identity.")
    decision: Literal["approved", "rejected"]
    comment: str | None = None


class ApprovalInboxItem(BaseModel):
    approval_request: ApprovalRequest
    brief: Brief


class ApprovalInboxCount(BaseModel):
    count: int


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
