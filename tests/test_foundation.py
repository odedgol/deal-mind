from pathlib import Path

from cato_deal_intel.retrieval.sources.data import SourceData
from cato_deal_intel.security.authorization import authorize

ROOT = Path(__file__).parents[1] / "synthetic_data"


def test_source_data_loads_all_opportunities_and_generated_updates() -> None:
    source = SourceData(ROOT)

    assert {item.opportunity_id for item in source.opportunities()} == {
        "OPP-1001",
        "OPP-1002",
        "OPP-1003",
    }
    slack = [item for item in source.evidence() if item.source_type == "slack"]
    assert len(slack) >= 2 * 3
    assert all("SYNTHETIC" in item.metadata["synthetic_notice"] for item in slack)


def test_source_data_indexes_opportunities_and_permissions() -> None:
    source = SourceData(ROOT)

    assert source.opportunity("OPP-1001").account_id == "ACC-2001"
    assert source.opportunity("OPP-404") is None
    assert source.permission_profile("USR-5003").role == "Restricted Account Owner"
    assert source.permission_profile("USR-404") is None


def test_authorized_user_gets_source_and_access_filters() -> None:
    source = SourceData(ROOT)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1003")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5003")

    decision = authorize(opportunity, requester)

    assert decision.allowed is True
    assert "sensitive" in decision.allowed_access_levels
    assert "pricing" in decision.allowed_source_types


def test_unauthorized_user_receives_generic_denial() -> None:
    source = SourceData(ROOT)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1003")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5007")

    decision = authorize(opportunity, requester)

    assert decision.allowed is False
    assert decision.account_id is None
    assert decision.allowed_source_types == set()
    assert "Eclipse" not in decision.reason
