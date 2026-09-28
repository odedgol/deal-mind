from pathlib import Path
from threading import Lock

from ..models import Opportunity, PermissionProfile
from ..orchestration.services import (
    ApprovalRequestService,
    DealService,
    EvidenceServiceFactory,
    RunArtifactService,
)
from ..repositories.contracts import EvidenceRepository
from ..retrieval.embeddings import configured_embedding_provider
from ..retrieval.evidence_retriever import EvidenceRetriever
from ..retrieval.sources.data import SourceData
from ..security.authorization import authorize
from ..storage.approval_store import ApprovalStore
from ..storage.artifact_store import ArtifactStore
from ..storage.client_factory import QdrantClientFactory
from ..storage.paths import QDRANT_PATH, RUN_ARTIFACTS_PATH, SOURCE_DATA_PATH

SOURCE_DATA_ROOT = SOURCE_DATA_PATH
ARTIFACTS_ROOT = RUN_ARTIFACTS_PATH
RUN_ARTIFACT_SERVICE = RunArtifactService(ArtifactStore(ARTIFACTS_ROOT))
DEFAULT_QDRANT_PATH = QDRANT_PATH
DEAL_REPOSITORY = SourceData(SOURCE_DATA_ROOT)
APPROVAL_SERVICE = ApprovalRequestService(ApprovalStore(Path(ARTIFACTS_ROOT)))
QDRANT_CLIENTS = QdrantClientFactory(DEFAULT_QDRANT_PATH)
EVIDENCE_REPOSITORY: EvidenceRepository = EvidenceRetriever(
    client=QDRANT_CLIENTS(),
    path=DEFAULT_QDRANT_PATH,
    require_existing=True,
    embedding_provider=configured_embedding_provider(),
)
DEAL_SERVICE = DealService(DEAL_REPOSITORY)
EVIDENCE_SERVICE_FACTORY = EvidenceServiceFactory(EVIDENCE_REPOSITORY)
APPROVAL_LOCK = Lock()


def permission_profile(user_id: str) -> PermissionProfile | None:
    return DEAL_SERVICE.permission_profile(user_id)


def is_deal_desk_approver(profile: PermissionProfile | None) -> bool:
    return profile is not None and profile.role == "Deal Desk Approver"


def eligible_approvers(
    opportunity: Opportunity | None,
    profiles: list[PermissionProfile],
    requester_user_id: str,
) -> list[str]:
    if opportunity is None:
        return []
    return [
        profile.user_id
        for profile in profiles
        if profile.user_id != requester_user_id
        and is_deal_desk_approver(profile)
        and authorize(opportunity, profile).allowed
    ]


def requester_is_only_eligible_approver(
    opportunity_id: str,
    requester_user_id: str,
) -> bool:
    opportunity = DEAL_SERVICE.opportunity(opportunity_id)

    if opportunity is None or not opportunity.approval_required:
        return False

    requester = DEAL_SERVICE.permission_profile(requester_user_id)
    if not authorize(opportunity, requester).allowed:
        return False

    other_approvers = eligible_approvers(
        opportunity=opportunity,
        profiles=DEAL_SERVICE.permissions(),
        requester_user_id=requester_user_id,
    )

    return not other_approvers
