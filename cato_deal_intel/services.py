from datetime import UTC, datetime
from typing import Literal

from .authorization import authorize
from .data import SourceData
from .models import (
    AgentOutput,
    ApprovalRecord,
    AuthorizationDecision,
    Brief,
    DealSnapshot,
    EvidenceItem,
    Opportunity,
    PermissionProfile,
    RecommendedAction,
    StrategyOutput,
)
from .retrieval import EvidenceRetriever, RetrievalRequest


class DealService:
    def __init__(self, source: SourceData) -> None:
        self.source = source

    def authorize(
        self, opportunity_id: str, user_id: str
    ) -> tuple[Opportunity, AuthorizationDecision]:
        opportunity = self._find_opportunity(opportunity_id)
        requester = self._find_requester(user_id)
        decision = authorize(opportunity, requester)
        return opportunity, decision

    def _find_opportunity(self, opportunity_id: str) -> Opportunity:
        match = next(
            (item for item in self.source.opportunities() if item.opportunity_id == opportunity_id),
            None,
        )
        if match is None:
            raise ValueError("Opportunity was not found.")
        return match

    def _find_requester(self, user_id: str) -> PermissionProfile | None:
        return next((item for item in self.source.permissions() if item.user_id == user_id), None)


class EvidenceService:
    SEARCH_QUERY = "buyer goals objections urgency stakeholders negotiation risks pricing legal"
    SLACK_QUERY = "synthetic account team dashboard escalation conflict"

    def __init__(self, source: SourceData, retriever: EvidenceRetriever) -> None:
        self.source = source
        self.retriever = retriever

    def retrieve(self, opportunity_id: str, decision: AuthorizationDecision) -> list[EvidenceItem]:
        results = self.search(
            opportunity_id=opportunity_id,
            query=self.SEARCH_QUERY,
            decision=decision,
            limit=8,
        )
        return self._include_slack_context(results, opportunity_id, decision)

    def search(
        self,
        *,
        opportunity_id: str,
        query: str,
        decision: AuthorizationDecision,
        limit: int = 8,
    ) -> list[EvidenceItem]:
        return self.retriever.retrieve(
            RetrievalRequest(
                query=query,
                opportunity_id=opportunity_id,
                allowed_source_types=decision.allowed_source_types,
                allowed_access_levels=decision.allowed_access_levels,
                limit=limit,
            ),
            decision,
        )

    def _include_slack_context(
        self,
        evidence: list[EvidenceItem],
        opportunity_id: str,
        decision: AuthorizationDecision,
    ) -> list[EvidenceItem]:
        if any(item.source_type == "slack" for item in evidence):
            return evidence
        updates = self.retriever.retrieve(
            RetrievalRequest(
                query=self.SLACK_QUERY,
                opportunity_id=opportunity_id,
                allowed_source_types=decision.allowed_source_types,
                allowed_access_levels=decision.allowed_access_levels,
                limit=2,
            ),
            decision,
        )
        return evidence + [item for item in updates if item.source_type == "slack"]


class ApprovalService:
    def prepare(
        self,
        opportunity: Opportunity,
        actions: list[RecommendedAction],
        decision: Literal["approved", "rejected", "pending"],
    ) -> tuple[list[RecommendedAction], list[ApprovalRecord]]:
        routed_actions = self._route(opportunity, actions)
        approvals = [
            ApprovalRecord(
                recommendation=action.action,
                reason="Sensitive opportunity recommendation requires human review.",
                decision=decision if action.requires_approval else "approved",
                timestamp=datetime.now(UTC),
            )
            for action in routed_actions
            if action.requires_approval
        ]
        return routed_actions, approvals

    @staticmethod
    def _route(
        opportunity: Opportunity, actions: list[RecommendedAction]
    ) -> list[RecommendedAction]:
        if not opportunity.approval_required:
            return actions
        return [action.model_copy(update={"requires_approval": True}) for action in actions]


def build_brief(
    *,
    run_id: str,
    opportunity: Opportunity,
    evidence: list[EvidenceItem],
    deal_snapshot: DealSnapshot,
    conversation: AgentOutput,
    stakeholders: AgentOutput,
    strategy: StrategyOutput,
    actions: list[RecommendedAction],
    approvals: list[ApprovalRecord],
) -> Brief:
    warnings = strategy.warnings + [
        f"Approval required: {approval.recommendation}"
        for approval in approvals
        if approval.decision == "pending"
    ]
    return Brief(
        run_id=run_id,
        opportunity_id=opportunity.opportunity_id,
        deal_snapshot=deal_snapshot,
        executive_summary=strategy.summary,
        buyer_goals=conversation.findings,
        stakeholder_map=stakeholders.findings,
        negotiation_state=conversation.findings,
        recommended_next_actions=actions,
        missing_information=conversation.missing_information + stakeholders.missing_information,
        source_evidence=evidence,
        confidence_and_review_warnings=warnings,
    )
