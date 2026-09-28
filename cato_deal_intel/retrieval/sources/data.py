from functools import cached_property
from pathlib import Path

from ...models import EvidenceItem, Opportunity, PermissionProfile
from .internal.gong import GongEvidenceLoader
from .internal.policy import PolicyEvidenceLoader
from .internal.pricing import PricingEvidenceLoader
from .internal.salesforce import SalesforceEvidenceLoader
from .internal.slack import SlackEvidenceLoader
from .parsing import parse_opportunity_row, parse_permission_row
from .reader import TsvReader


class SourceData:
    """Coordinate typed records and evidence loaders for local source data."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.reader = TsvReader(root)
        self.gong_loader = GongEvidenceLoader(root, self.reader, self._account_by_opportunity)
        self.policy_loader = PolicyEvidenceLoader(root)
        self.pricing_loader = PricingEvidenceLoader(self.reader, self._account_by_opportunity)
        self.salesforce_loader = SalesforceEvidenceLoader(
            self.reader,
            self._opportunity_by_account,
        )
        self.slack_loader = SlackEvidenceLoader(self.reader)

    def opportunities(self) -> list[Opportunity]:
        return list(self._opportunity_records)

    def opportunity(self, opportunity_id: str) -> Opportunity | None:
        """Return one opportunity by ID without scanning the full source list."""
        return self._opportunities_by_id.get(opportunity_id)

    def permissions(self) -> list[PermissionProfile]:
        return list(self._permission_records)

    def permission_profile(self, user_id: str) -> PermissionProfile | None:
        """Return one permission profile by user ID without scanning the full list."""
        return self._permissions_by_user_id.get(user_id)

    def evidence(self) -> list[EvidenceItem]:
        evidence = self._salesforce_evidence()
        evidence.extend(self._gong_evidence())
        evidence.extend(self._pricing_evidence())
        evidence.extend(self._policy_evidence())
        evidence.extend(self._slack_evidence())
        return evidence

    def _salesforce_evidence(self) -> list[EvidenceItem]:
        return self.salesforce_loader.load()

    def _gong_evidence(self) -> list[EvidenceItem]:
        return self.gong_loader.load()

    def _pricing_evidence(self) -> list[EvidenceItem]:
        return self.pricing_loader.load()

    def _policy_evidence(self) -> list[EvidenceItem]:
        return self.policy_loader.load()

    def _slack_evidence(self) -> list[EvidenceItem]:
        return self.slack_loader.load()

    @cached_property
    def _opportunity_records(self) -> list[Opportunity]:
        rows = self.reader.read("salesforce/opportunities.tsv")
        return [Opportunity.model_validate(parse_opportunity_row(row)) for row in rows]

    @cached_property
    def _permission_records(self) -> list[PermissionProfile]:
        rows = self.reader.read("policies/access_permissions.tsv")
        return [PermissionProfile.model_validate(parse_permission_row(row)) for row in rows]

    @cached_property
    def _opportunities_by_id(self) -> dict[str, Opportunity]:
        return {item.opportunity_id: item for item in self._opportunity_records}

    @cached_property
    def _permissions_by_user_id(self) -> dict[str, PermissionProfile]:
        return {item.user_id: item for item in self._permission_records}

    @cached_property
    def _opportunity_by_account(self) -> dict[str, str]:
        return {item.account_id: item.opportunity_id for item in self._opportunity_records}

    @cached_property
    def _account_by_opportunity(self) -> dict[str, str]:
        return {item.opportunity_id: item.account_id for item in self._opportunity_records}
