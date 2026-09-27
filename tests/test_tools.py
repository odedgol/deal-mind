from pathlib import Path

from cato_deal_intel.agents.tools import (
    AuthorizedEvidenceSearchTool,
    DealContextTool,
    EvidenceSearchRequest,
)
from cato_deal_intel.orchestration.services import EvidenceService
from cato_deal_intel.retrieval.index import EvidenceRetriever
from cato_deal_intel.retrieval.sources.data import SourceData
from cato_deal_intel.security.authorization import authorize

ROOT = Path(__file__).parents[1] / "synthetic_data"


def test_evidence_tool_uses_bound_authorization() -> None:
    source = SourceData(ROOT)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1003")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5007")
    decision = authorize(opportunity, requester)
    tool = AuthorizedEvidenceSearchTool(EvidenceService(source, EvidenceRetriever()), decision)

    result = tool.run(EvidenceSearchRequest("OPP-1003", "restricted pricing"))

    assert result == []


def test_deal_context_tool_returns_canonical_snapshot() -> None:
    source = SourceData(ROOT)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1001")

    result = DealContextTool(opportunity).run()

    assert result.opportunity_id == "OPP-1001"
    assert result.amount_acv == opportunity.acv
