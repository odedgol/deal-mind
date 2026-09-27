from typing import Literal, Protocol

from ..models import (
    AgentOutput,
    AgentTrace,
    ApprovalRecord,
    ApprovalRequest,
    AuthorizationDecision,
    Brief,
    EvidenceItem,
    Opportunity,
    PermissionProfile,
    RetrievalDebug,
    StrategyOutput,
)
from ..retrieval.index import RetrievalRequest


class DealRepository(Protocol):
    """Read-only access to deal and authorization source data."""

    def opportunity(self, opportunity_id: str) -> Opportunity | None: ...

    def permission_profile(self, user_id: str) -> PermissionProfile | None: ...

    def permissions(self) -> list[PermissionProfile]: ...


class EvidenceRepository(Protocol):
    """Authorized semantic and lexical evidence retrieval."""

    def retrieve(
        self,
        request: RetrievalRequest,
        decision: AuthorizationDecision,
    ) -> list[EvidenceItem]: ...

    def retrieve_with_debug(
        self,
        request: RetrievalRequest,
        decision: AuthorizationDecision,
    ) -> tuple[list[EvidenceItem], RetrievalDebug]: ...


class ApprovalRepository(Protocol):
    """Persistence contract for human approval requests and decisions."""

    def create(self, request: ApprovalRequest) -> None: ...

    def inbox(self, user_id: str) -> list[tuple[ApprovalRequest, Brief]]: ...

    def requester_runs(self, user_id: str) -> list[Brief]: ...

    def decide(
        self,
        run_id: str,
        *,
        reviewer_user_id: str,
        decision: Literal["approved", "rejected"],
        comment: str | None,
    ) -> tuple[ApprovalRequest, Brief]: ...


class ArtifactRepository(Protocol):
    """Persistence contract for completed and failed workflow runs."""

    def find_brief(self, run_id: str) -> Brief | None: ...

    def save_run(
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
    ) -> None: ...

    def save_failure_trace(
        self,
        *,
        run_id: str,
        opportunity_id: str,
        user_id: str,
        traces: list[AgentTrace],
        error: Exception,
    ) -> None: ...
