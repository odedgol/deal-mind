from pathlib import Path

import pytest

from cato_deal_intel.agents.tools import (
    AuthorizedEvidenceSearchTool,
    DealContextTool,
    DealDeskPolicyTool,
    EvidenceSearchRequest,
    RecommendationValidationTool,
)
from cato_deal_intel.models import EvidenceItem, Finding, StrategyOutput
from cato_deal_intel.orchestration.services import EvidenceService
from cato_deal_intel.retrieval.evidence_retriever import EvidenceRetriever
from cato_deal_intel.retrieval.sources.data import SourceData
from cato_deal_intel.security.authorization import authorize

ROOT = Path(__file__).parents[1] / "synthetic_data"


def test_evidence_tool_uses_bound_authorization() -> None:
    source = SourceData(ROOT)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1003")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5007")
    decision = authorize(opportunity, requester)
    tool = AuthorizedEvidenceSearchTool(EvidenceService(EvidenceRetriever()), decision)

    result = tool.run(EvidenceSearchRequest("OPP-1003", "restricted pricing"))

    assert result == []


def test_deal_context_tool_returns_canonical_snapshot() -> None:
    source = SourceData(ROOT)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1001")

    result = DealContextTool(opportunity).run()

    assert result.opportunity_id == "OPP-1001"
    assert result.amount_acv == opportunity.acv


def test_policy_tool_explicitly_retrieves_shared_policy() -> None:
    source = SourceData(ROOT)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1001")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5001")
    decision = authorize(opportunity, requester)
    retriever = EvidenceRetriever()
    retriever.index(source.evidence())
    tool = DealDeskPolicyTool(EvidenceService(retriever), decision)

    result = tool.run()

    assert result is not None
    assert result.evidence_id == "policy:deal-desk"
    assert result.source_type == "policies"
    assert result.opportunity_id == "*"


def test_recommendation_validation_rejects_unknown_negotiation_state_citation() -> None:
    evidence = EvidenceItem(
        evidence_id="gong:CALL-001",
        opportunity_id="OPP-1001",
        account_id="ACC-1001",
        source_type="gong",
        source_file="gong/calls.tsv",
        source_id="CALL-001",
        access_level="standard",
        text="The buyer requested a discount.",
    )
    strategy = StrategyOutput(
        summary="The discount request is unresolved.",
        summary_evidence_ids=[evidence.evidence_id],
        negotiation_state=[
            Finding(
                text="The discount is pending approval.",
                evidence_ids=["invented:E-999"],
                confidence=0.8,
            )
        ],
        actions=[],
    )

    with pytest.raises(ValueError, match="invented:E-999"):
        RecommendationValidationTool().run(strategy, [evidence])
