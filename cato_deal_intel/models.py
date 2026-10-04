from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EvidenceItem(StrictModel):
    evidence_id: str
    opportunity_id: str
    account_id: str | None = None
    source_type: str
    source_file: str
    source_id: str
    access_level: str
    event_date: date | None = None
    text: str
    metadata: dict[str, str] = Field(default_factory=dict)


class Finding(StrictModel):
    text: str
    evidence_ids: list[str]
    confidence: float = Field(ge=0, le=1)
    uncertainty: str | None = None


class Opportunity(StrictModel):
    opportunity_id: str
    opportunity_name: str
    account_id: str
    account_name: str
    stage: str
    type: str
    region: str
    country: str
    industry: str
    owner: str
    close_date: date
    acv: int
    tcv: int
    renewal_term_months: int
    probability: int
    forecast_category: str
    next_step: str
    primary_competitor: str
    risk_level: str
    approval_required: bool
    restricted_access: bool


class PermissionProfile(StrictModel):
    user_id: str
    user_name: str
    role: str
    allowed_account_ids: set[str]
    allowed_source_types: set[str]
    can_view_sensitive_pricing: bool
    can_request_approval: bool
    can_view_restricted_account: bool


class AuthorizationDecision(StrictModel):
    allowed: bool
    reason: str
    opportunity_id: str
    user_id: str
    account_id: str | None = None
    allowed_source_types: set[str] = Field(default_factory=set)
    allowed_access_levels: set[str] = Field(default_factory=set)


class AgentTrace(StrictModel):
    trace_id: str
    run_id: str
    event_type: Literal["agent", "retrieval", "tool", "approval", "recommendation"]
    name: str
    prompt_version: str
    status: Literal["started", "completed", "failed"]
    started_at: datetime
    completed_at: datetime | None = None
    error: str | None = None
    metadata: dict[str, str] = Field(default_factory=dict)


class DealSnapshot(StrictModel):
    opportunity_id: str
    account_name: str
    stage: str
    amount_acv: int
    close_date: date
    owner: str
    risk_level: str
    evidence_ids: list[str]


class AgentOutput(StrictModel):
    findings: list[Finding]
    missing_information: list[str] = Field(default_factory=list)


class RecommendedAction(StrictModel):
    action: str
    owner: str
    rationale: str
    evidence_ids: list[str]
    requires_approval: bool


class StrategyOutput(StrictModel):
    summary: str
    summary_evidence_ids: list[str] = Field(default_factory=list)
    negotiation_state: list[Finding]
    actions: list[RecommendedAction]
    warnings: list[str] = Field(default_factory=list)


class CostSummary(StrictModel):
    budget_usd: float | None = None
    spent_usd: float = 0.0
    run_spent_usd: float = 0.0
    remaining_usd: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    call_count: int = 0
    models: list[str] = Field(default_factory=list)
    period_key: str | None = None


class RetrievalDebug(StrictModel):
    """Safe counts that explain how an authorized retrieval was narrowed."""

    query: str
    opportunity_id: str
    authorized_candidates: int
    dense_candidates: int
    final_results: int
    final_evidence_ids: list[str] = Field(default_factory=list)
    allowed_source_types: list[str] = Field(default_factory=list)


class ApprovalRecord(StrictModel):
    recommendation: str
    reason: str
    decision: Literal["approved", "rejected", "pending"]
    comment: str | None = None
    timestamp: datetime


class ApprovalRequest(StrictModel):
    run_id: str
    opportunity_id: str
    requester_user_id: str
    requester_name: str
    eligible_approver_user_ids: list[str]
    status: Literal["pending", "approved", "rejected"] = "pending"
    requested_actions: list[str] = Field(default_factory=list)
    requested_at: datetime
    reviewer_user_id: str | None = None
    comment: str | None = None
    decided_at: datetime | None = None


class Brief(StrictModel):
    run_id: str
    opportunity_id: str
    run_status: Literal["completed", "awaiting_approval", "rejected"] = "completed"
    deal_snapshot: DealSnapshot
    executive_summary: str
    executive_summary_evidence_ids: list[str] = Field(default_factory=list)
    buyer_goals: list[Finding]
    stakeholder_map: list[Finding]
    negotiation_state: list[Finding]
    recommended_next_actions: list[RecommendedAction]
    missing_information: list[str]
    source_evidence: list[EvidenceItem]
    confidence_and_review_warnings: list[str]
    retrieval_debug: list[RetrievalDebug] = Field(default_factory=list)
    cost_summary: CostSummary = Field(default_factory=CostSummary)


class DeniedResult(StrictModel):
    """Safe workflow result returned when authorization is denied."""

    run_id: str
    opportunity_id: str
    user_id: str
    status: Literal["denied"] = "denied"
    message: str


WorkflowResult = Brief | DeniedResult
