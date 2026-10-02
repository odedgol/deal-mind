from collections.abc import Callable
from dataclasses import dataclass

from ..models import (
    AuthorizationDecision,
    DealSnapshot,
    EvidenceItem,
    Opportunity,
    RecommendedAction,
    StrategyOutput,
)
from ..observability.tracing import AgentTraceCollector, trace_operation
from ..orchestration.services import ApprovalService, EvidenceService
from ..security.validation import validate_citations


def _trace_tool[T](
    *,
    collector: AgentTraceCollector | None,
    run_id: str | None,
    name: str,
    operation: Callable[[], T],
    metadata: dict[str, str] | None = None,
) -> T:
    if collector is None or run_id is None:
        return operation()
    result, _ = trace_operation(
        collector=collector,
        run_id=run_id,
        event_type="tool",
        name=name,
        operation=operation,
        metadata=metadata,
    )
    return result


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

    def __init__(
        self,
        service: EvidenceService,
        decision: AuthorizationDecision,
        collector: AgentTraceCollector | None = None,
        run_id: str | None = None,
    ) -> None:
        self.service = service
        self.decision = decision
        self.collector = collector
        self.run_id = run_id
        self.retrieved_evidence: list[EvidenceItem] = []

    def run(self, request: EvidenceSearchRequest) -> list[EvidenceItem]:
        results = _trace_tool(
            collector=self.collector,
            run_id=self.run_id,
            name="search_authorized_evidence",
            operation=lambda: self.service.search(
                opportunity_id=request.opportunity_id,
                query=request.query,
                decision=self.decision,
                limit=request.limit,
            ),
        )
        self.retrieved_evidence.extend(results)
        return results


class DealContextTool:
    name = "get_opportunity_snapshot"

    def __init__(
        self,
        opportunity: Opportunity,
        collector: AgentTraceCollector | None = None,
        run_id: str | None = None,
    ) -> None:
        self.opportunity = opportunity
        self.collector = collector
        self.run_id = run_id

    def run(self) -> DealSnapshot:
        return _trace_tool(
            collector=self.collector,
            run_id=self.run_id,
            name="get_opportunity_snapshot",
            operation=lambda: DealSnapshot(
                opportunity_id=self.opportunity.opportunity_id,
                account_name=self.opportunity.account_name,
                stage=self.opportunity.stage,
                amount_acv=self.opportunity.acv,
                close_date=self.opportunity.close_date,
                owner=self.opportunity.owner,
                risk_level=self.opportunity.risk_level,
                evidence_ids=[],
            ),
        )


class DealDeskPolicyTool:
    name = "get_deal_desk_policy"

    def __init__(
        self,
        service: EvidenceService,
        decision: AuthorizationDecision,
        collector: AgentTraceCollector | None = None,
        run_id: str | None = None,
    ) -> None:
        self.service = service
        self.decision = decision
        self.collector = collector
        self.run_id = run_id
        self.retrieved_evidence: list[EvidenceItem] = []

    def run(self) -> EvidenceItem | None:
        policy = _trace_tool(
            collector=self.collector,
            run_id=self.run_id,
            name="get_deal_desk_policy",
            operation=lambda: self.service.search_shared_policy(
                query="discount legal terms approval policy",
                decision=self.decision,
                limit=4,
            ),
        )
        result = next((item for item in policy if item.source_type == "policies"), None)
        if result is not None and result.evidence_id not in {
            item.evidence_id for item in self.retrieved_evidence
        }:
            self.retrieved_evidence.append(result)
        return result


class ApprovalRequestTool:
    name = "request_approval"

    def __init__(
        self,
        service: ApprovalService,
        collector: AgentTraceCollector | None = None,
        run_id: str | None = None,
    ) -> None:
        self.service = service
        self.collector = collector
        self.run_id = run_id

    def run(
        self,
        opportunity: Opportunity,
        actions: list[RecommendedAction],
    ) -> list[RecommendedAction]:
        routed, _ = _trace_tool(
            collector=self.collector,
            run_id=self.run_id,
            name="request_approval",
            operation=lambda: self.service.prepare(opportunity, actions, "pending"),
            metadata={"action_count": str(len(actions))},
        )
        return routed


class RecommendationValidationTool:
    name = "validate_recommendation"

    def __init__(
        self, collector: AgentTraceCollector | None = None, run_id: str | None = None
    ) -> None:
        self.collector = collector
        self.run_id = run_id

    def run(
        self,
        recommendation: StrategyOutput,
        evidence: list[EvidenceItem],
    ) -> StrategyOutput:
        _trace_tool(
            collector=self.collector,
            run_id=self.run_id,
            name="validate_recommendation",
            operation=lambda: validate_citations([recommendation], evidence),
            metadata={
                "citation_count": str(
                    sum(len(item.evidence_ids) for item in recommendation.actions)
                    + sum(len(item.evidence_ids) for item in recommendation.negotiation_state)
                )
            },
        )
        return recommendation


DEAL_CONTEXT_TOOLS = (
    ToolSpec("get_opportunity_snapshot", "Read the canonical opportunity facts."),
)

CONVERSATION_TOOLS = (
    ToolSpec("search_authorized_evidence", "Search authorized Gong and Slack evidence."),
)

STAKEHOLDER_TOOLS = (
    ToolSpec("search_authorized_evidence", "Search authorized stakeholder signals."),
)

STRATEGY_TOOLS = (
    ToolSpec("get_deal_desk_policy", "Read the relevant approval policy."),
    ToolSpec("validate_recommendation", "Validate citations and approval requirements."),
    ToolSpec("request_approval", "Create a human approval request."),
)
