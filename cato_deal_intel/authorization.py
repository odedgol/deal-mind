from .models import AuthorizationDecision, Opportunity, PermissionProfile


def authorize(
    opportunity: Opportunity,
    requester: PermissionProfile | None,
) -> AuthorizationDecision:
    if requester is None:
        return AuthorizationDecision(
            allowed=False,
            reason="Requester is not authorized for this request.",
            opportunity_id=opportunity.opportunity_id,
            user_id="unknown",
        )
    if opportunity.account_id not in requester.allowed_account_ids:
        return _denied(opportunity, requester, "Requester is not authorized for this account.")
    if opportunity.restricted_access and not requester.can_view_restricted_account:
        return _denied(opportunity, requester, "Requester is not authorized for this account.")
    access_levels = {"standard"}
    if requester.can_view_sensitive_pricing:
        access_levels.add("sensitive")
    return AuthorizationDecision(
        allowed=True,
        reason="Authorized.",
        opportunity_id=opportunity.opportunity_id,
        user_id=requester.user_id,
        account_id=opportunity.account_id,
        allowed_source_types=requester.allowed_source_types,
        allowed_access_levels=access_levels,
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
