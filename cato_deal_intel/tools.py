from dataclasses import dataclass

from .models import (
    AuthorizationDecision,
    DealSnapshot,
    EvidenceItem,
    Opportunity,
    RecommendedAction,
    StrategyOutput,
)
from .services import ApprovalService, EvidenceService
from .validation import validate_citations


@dataclass(frozen=True)
class ToolSpec:
    """The small, explicit tool contract exposed to an agent."""

    name: str
    description: str


@dataclass(frozen=True)
class EvidenceSearchRequest:
    opportunity_id: str
    query: str
    limit: int = 8


class AuthorizedEvidenceSearchTool:
    name = "search_authorized_evidence"

    def __init__(self, service: EvidenceService, decision: AuthorizationDecision) -> None:
        self.service = service
        self.decision = decision
        self.retrieved_evidence: list[EvidenceItem] = []

    def run(self, request: EvidenceSearchRequest) -> list[EvidenceItem]:
        results = self.service.search(
            opportunity_id=request.opportunity_id,
            query=request.query,
            decision=self.decision,
            limit=request.limit,
        )
        known_ids = {item.evidence_id for item in self.retrieved_evidence}
        self.retrieved_evidence.extend(
            item for item in results if item.evidence_id not in known_ids
        )
        return results


class DealContextTool:
    name = "get_opportunity_snapshot"

    def __init__(self, opportunity: Opportunity) -> None:
        self.opportunity = opportunity

    def run(self) -> DealSnapshot:
        return DealSnapshot(
            opportunity_id=self.opportunity.opportunity_id,
            account_name=self.opportunity.account_name,
            stage=self.opportunity.stage,
            amount_acv=self.opportunity.acv,
            close_date=self.opportunity.close_date,
            owner=self.opportunity.owner,
            risk_level=self.opportunity.risk_level,
            evidence_ids=[],
        )


class DealDeskPolicyTool:
    name = "get_deal_desk_policy"

    def __init__(self, service: EvidenceService, decision: AuthorizationDecision) -> None:
        self.service = service
        self.decision = decision
        self.retrieved_evidence: list[EvidenceItem] = []

    def run(self, opportunity_id: str) -> EvidenceItem | None:
        policy = self.service.search(
            opportunity_id=opportunity_id,
            query="discount legal terms approval policy",
            decision=self.decision,
            limit=4,
        )
        result = next((item for item in policy if item.source_type == "policies"), None)
        if result is not None and result.evidence_id not in {
            item.evidence_id for item in self.retrieved_evidence
        }:
            self.retrieved_evidence.append(result)
        return result


class ApprovalRequestTool:
    name = "request_approval"

    def __init__(self, service: ApprovalService) -> None:
        self.service = service

    def run(
        self,
        opportunity: Opportunity,
        actions: list[RecommendedAction],
    ) -> list[RecommendedAction]:
        routed, _ = self.service.prepare(opportunity, actions, "pending")
        return routed


class RecommendationValidationTool:
    name = "validate_recommendation"

    def run(
        self,
        recommendation: StrategyOutput,
        evidence: list[EvidenceItem],
    ) -> StrategyOutput:
        validate_citations([recommendation], evidence)
        return recommendation


DEAL_CONTEXT_TOOLS = (
    ToolSpec("get_opportunity_snapshot", "Read the canonical opportunity facts."),
    ToolSpec("get_account_snapshot", "Read the authorized account facts."),
    ToolSpec("get_contacts", "Read authorized contacts for the account."),
)

CONVERSATION_TOOLS = (
    ToolSpec("search_authorized_evidence", "Search authorized Gong and Slack evidence."),
    ToolSpec("get_call_transcript", "Read an authorized call transcript."),
)

STAKEHOLDER_TOOLS = (
    ToolSpec("get_contacts", "Read authorized contacts and deal roles."),
    ToolSpec("get_call_participants", "Read authorized call participants."),
    ToolSpec("search_authorized_evidence", "Search authorized stakeholder signals."),
)

STRATEGY_TOOLS = (
    ToolSpec("get_deal_desk_policy", "Read the relevant approval policy."),
    ToolSpec("validate_recommendation", "Validate citations and approval requirements."),
    ToolSpec("request_approval", "Create a human approval request."),
)
