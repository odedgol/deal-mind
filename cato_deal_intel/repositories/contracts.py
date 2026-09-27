from typing import Literal, Protocol

from ..models import (
    ApprovalRequest,
    AuthorizationDecision,
    Brief,
    EvidenceItem,
    Opportunity,
    PermissionProfile,
    RetrievalDebug,
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
