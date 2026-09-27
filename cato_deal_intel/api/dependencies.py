from pathlib import Path
from threading import Lock

from ..models import Opportunity, PermissionProfile
from ..repositories.contracts import ApprovalRepository
from ..retrieval.sources.data import SourceData
from ..security.authorization import authorize
from ..storage.approval_store import ApprovalStore
from ..storage.client_factory import QdrantClientFactory
from ..storage.paths import QDRANT_PATH, RUN_ARTIFACTS_PATH, SOURCE_DATA_PATH

DATA_ROOT = SOURCE_DATA_PATH
ARTIFACT_ROOT = RUN_ARTIFACTS_PATH
DEFAULT_QDRANT_PATH = QDRANT_PATH
SOURCE = SourceData(DATA_ROOT)
APPROVAL_STORE: ApprovalRepository = ApprovalStore(Path(ARTIFACT_ROOT))
QDRANT_CLIENTS = QdrantClientFactory(DEFAULT_QDRANT_PATH)
APPROVAL_LOCK = Lock()


def permission_profile(user_id: str) -> PermissionProfile | None:
    return SOURCE.permission_profile(user_id)


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
    opportunity = SOURCE.opportunity(opportunity_id)

    if opportunity is None or not opportunity.approval_required:
        return False

    requester = SOURCE.permission_profile(requester_user_id)
    if not authorize(opportunity, requester).allowed:
        return False

    other_approvers = eligible_approvers(
        opportunity=opportunity,
        profiles=SOURCE.permissions(),
        requester_user_id=requester_user_id,
    )

    return not other_approvers
