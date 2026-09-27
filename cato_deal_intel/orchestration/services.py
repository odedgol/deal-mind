from datetime import UTC, datetime
from typing import Literal, cast

from ..models import (
    AgentOutput,
    AgentTrace,
    ApprovalRecord,
    ApprovalRequest,
    AuthorizationDecision,
    Brief,
    CostSummary,
    DealSnapshot,
    EvidenceItem,
    Opportunity,
    PermissionProfile,
    RecommendedAction,
    RetrievalDebug,
    StrategyOutput,
)
from ..observability.tracing import AgentTraceCollector, trace_operation
from ..repositories.contracts import (
    ApprovalRepository,
    ArtifactRepository,
    DealRepository,
    EvidenceRepository,
)
from ..retrieval.index import RetrievalRequest
from ..security.authorization import authorize


class RunArtifactService:
    """Application boundary for persisting successful and failed workflow runs."""

    def __init__(self, repository: ArtifactRepository) -> None:
        self.repository = repository

    def find_brief(self, run_id: str) -> Brief | None:
        return self.repository.find_brief(run_id)

    def save_completed_run(
        self,
        *,
        run_id: str,
        requester_user_id: str,
        opportunity: Opportunity,
        decision: AuthorizationDecision,
        evidence: list[EvidenceItem],
        conversation: AgentOutput,
        stakeholders: AgentOutput,
        strategy: StrategyOutput,
        approvals: list[ApprovalRecord],
        brief: Brief,
        traces: list[AgentTrace],
    ) -> None:
        self.repository.save_run(
            run_id=run_id,
            requester_user_id=requester_user_id,
            opportunity=opportunity,
            decision=decision,
            evidence=evidence,
            conversation=conversation,
            stakeholders=stakeholders,
            strategy=strategy,
            approvals=approvals,
            brief=brief,
            traces=traces,
        )

    def save_failed_run(
        self,
        *,
        run_id: str,
        opportunity_id: str,
        user_id: str,
        traces: list[AgentTrace],
        error: Exception,
    ) -> None:
        self.repository.save_failure_trace(
            run_id=run_id,
            opportunity_id=opportunity_id,
            user_id=user_id,
            traces=traces,
            error=error,
        )


class ApprovalRequestService:
    """Application boundary for approval request persistence and decisions."""

    def __init__(self, repository: ApprovalRepository) -> None:
        self.repository = repository

    def create(self, request: ApprovalRequest) -> None:
        self.repository.create(request)

    def inbox(self, user_id: str) -> list[tuple[ApprovalRequest, Brief]]:
        return self.repository.inbox(user_id)

    def requester_runs(self, user_id: str) -> list[Brief]:
        return self.repository.requester_runs(user_id)

    def decide(
        self,
        run_id: str,
        *,
        reviewer_user_id: str,
        decision: Literal["approved", "rejected"],
        comment: str | None,
    ) -> tuple[ApprovalRequest, Brief]:
        return self.repository.decide(
            run_id,
            reviewer_user_id=reviewer_user_id,
            decision=decision,
            comment=comment,
        )


class DealService:
    def __init__(self, deal_repository: DealRepository) -> None:
        self.deal_repository = deal_repository

    def authorize(
        self, opportunity_id: str, user_id: str
    ) -> tuple[Opportunity, AuthorizationDecision]:
        opportunity = self._find_opportunity(opportunity_id)
        requester = self._find_requester(user_id)
        decision = authorize(opportunity, requester)
        return opportunity, decision

    def _find_opportunity(self, opportunity_id: str) -> Opportunity:
        match = self.deal_repository.opportunity(opportunity_id)
        if match is None:
            raise ValueError("Opportunity was not found.")
        return match

    def _find_requester(self, user_id: str) -> PermissionProfile | None:
        return self.deal_repository.permission_profile(user_id)


class EvidenceService:
    SEARCH_QUERY = "buyer goals objections urgency stakeholders negotiation risks pricing legal"
    SLACK_QUERY = "synthetic account team dashboard escalation conflict"

    def __init__(
        self,
        deal_repository: DealRepository,
        retriever: EvidenceRepository,
        collector: AgentTraceCollector | None = None,
        run_id: str | None = None,
        retrieval_debug: list[RetrievalDebug] | None = None,
    ) -> None:
        self.deal_repository = deal_repository
        self.retriever = retriever
        self.collector = collector
        self.run_id = run_id
        self.retrieval_debug = retrieval_debug if retrieval_debug is not None else []

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
        request = RetrievalRequest(
            query=query,
            opportunity_id=opportunity_id,
            allowed_source_types=decision.allowed_source_types,
            allowed_access_levels=decision.allowed_access_levels,
            limit=limit,
        )

        def retrieve() -> tuple[list[EvidenceItem], RetrievalDebug | None]:
            retrieve_with_debug = getattr(self.retriever, "retrieve_with_debug", None)
            if callable(retrieve_with_debug):
                return cast(
                    tuple[list[EvidenceItem], RetrievalDebug],
                    retrieve_with_debug(request, decision),
                )
            return self.retriever.retrieve(request, decision), None

        if self.collector is None or self.run_id is None:
            results, debug = retrieve()
            if debug is not None:
                self.retrieval_debug.append(debug)
            return results
        (results, debug), _ = trace_operation(
            collector=self.collector,
            run_id=self.run_id,
            event_type="retrieval",
            name="qdrant.retrieve",
            operation=retrieve,
            metadata={"opportunity_id": opportunity_id, "result_limit": str(limit)},
        )
        if debug is not None:
            self.retrieval_debug.append(debug)
        return results

    def _include_slack_context(
        self,
        evidence: list[EvidenceItem],
        opportunity_id: str,
        decision: AuthorizationDecision,
    ) -> list[EvidenceItem]:
        if any(item.source_type == "slack" for item in evidence):
            return evidence
        updates = self.search(
            opportunity_id=opportunity_id,
            query=self.SLACK_QUERY,
            decision=decision,
            limit=20,
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
    retrieval_debug: list[RetrievalDebug] | None = None,
    cost_summary: CostSummary | None = None,
) -> Brief:
    warnings = strategy.warnings + [
        f"Approval required: {approval.recommendation}"
        for approval in approvals
        if approval.decision == "pending"
    ]
    return Brief(
        run_id=run_id,
        opportunity_id=opportunity.opportunity_id,
        run_status=_brief_status(approvals),
        deal_snapshot=deal_snapshot,
        executive_summary=strategy.summary,
        executive_summary_evidence_ids=strategy.summary_evidence_ids,
        buyer_goals=conversation.findings,
        stakeholder_map=stakeholders.findings,
        negotiation_state=conversation.findings,
        recommended_next_actions=actions,
        missing_information=conversation.missing_information + stakeholders.missing_information,
        source_evidence=evidence,
        confidence_and_review_warnings=warnings,
        retrieval_debug=retrieval_debug or [],
        cost_summary=cost_summary or CostSummary(),
    )


def _brief_status(
    approvals: list[ApprovalRecord],
) -> Literal["completed", "awaiting_approval", "rejected"]:
    decisions = {approval.decision for approval in approvals}
    if "pending" in decisions:
        return "awaiting_approval"
    if "rejected" in decisions:
        return "rejected"
    return "completed"
