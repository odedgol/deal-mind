from ..models import AuthorizationDecision, Opportunity, PermissionProfile

AUTHORIZED_REASON = "Authorized."
UNAUTHORIZED_REQUESTER_REASON = "Requester is not authorized for this request."
UNAUTHORIZED_ACCOUNT_REASON = "Requester is not authorized for this account."


def authorize(
    opportunity: Opportunity,
    requester: PermissionProfile | None,
) -> AuthorizationDecision:
    if requester is None:
        return _denied_without_requester(opportunity)

    denial_reason = _denial_reason(opportunity, requester)
    if denial_reason is not None:
        return _denied(opportunity, requester, denial_reason)

    return _authorized(opportunity, requester)


def _denial_reason(
    opportunity: Opportunity,
    requester: PermissionProfile,
) -> str | None:
    if opportunity.account_id not in requester.allowed_account_ids:
        return UNAUTHORIZED_ACCOUNT_REASON
    if opportunity.restricted_access and not requester.can_view_restricted_account:
        return UNAUTHORIZED_ACCOUNT_REASON
    return None


def _authorized(
    opportunity: Opportunity,
    requester: PermissionProfile,
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=True,
        reason=AUTHORIZED_REASON,
        opportunity_id=opportunity.opportunity_id,
        user_id=requester.user_id,
        account_id=opportunity.account_id,
        allowed_source_types=requester.allowed_source_types,
        allowed_access_levels=_allowed_access_levels(requester),
    )


def _allowed_access_levels(requester: PermissionProfile) -> set[str]:
    access_levels = {"standard"}
    if requester.can_view_sensitive_pricing:
        access_levels.add("sensitive")
    if requester.can_view_restricted_account:
        access_levels.add("restricted")
    return access_levels


def _denied_without_requester(opportunity: Opportunity) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=False,
        reason=UNAUTHORIZED_REQUESTER_REASON,
        opportunity_id=opportunity.opportunity_id,
        user_id="unknown",
    )


def _denied(
    opportunity: Opportunity,
    requester: PermissionProfile,
    reason: str,
) -> AuthorizationDecision:
    return AuthorizationDecision(
        allowed=False,
        reason=reason,
        opportunity_id=opportunity.opportunity_id,
        user_id=requester.user_id,
    )
