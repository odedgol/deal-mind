from pathlib import Path

from cato_deal_intel.authorization import authorize
from cato_deal_intel.data import SourceData
from cato_deal_intel.retrieval import EvidenceRetriever, RetrievalRequest

ROOT = Path(__file__).parents[1] / "synthetic_data"


def _retriever(tmp_path: Path) -> tuple[SourceData, EvidenceRetriever]:
    source = SourceData(ROOT)
    retriever = EvidenceRetriever(path=tmp_path / "qdrant")
    retriever.index(source.evidence())
    return source, retriever


def test_retrieval_applies_opportunity_and_permission_filters(tmp_path: Path) -> None:
    source, retriever = _retriever(tmp_path)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1003")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5003")
    decision = authorize(opportunity, requester)

    results = retriever.retrieve(
        RetrievalRequest(
            query="discount legal approval",
            opportunity_id="OPP-1003",
            allowed_source_types=decision.allowed_source_types,
            allowed_access_levels=decision.allowed_access_levels,
        ),
        decision,
    )

    assert results
    assert all(item.opportunity_id in {"OPP-1003", "*"} for item in results)
    assert all(item.access_level in {"standard", "sensitive"} for item in results)


def test_restricted_opportunity_is_not_retrieved_for_insufficient_user(tmp_path: Path) -> None:
    source, retriever = _retriever(tmp_path)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1003")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5007")
    decision = authorize(opportunity, requester)

    results = retriever.retrieve(
        RetrievalRequest(
            query="restricted pricing liability",
            opportunity_id="OPP-1003",
            allowed_source_types=decision.allowed_source_types,
            allowed_access_levels=decision.allowed_access_levels,
        ),
        decision,
    )

    assert decision.allowed is False
    assert results == []


def test_hybrid_index_is_persistent_across_retriever_instances(tmp_path: Path) -> None:
    source = SourceData(ROOT)
    qdrant_path = tmp_path / "qdrant"
    EvidenceRetriever(path=qdrant_path).index(source.evidence())
    retriever = EvidenceRetriever(path=qdrant_path, require_existing=True)
    opportunity = next(item for item in source.opportunities() if item.opportunity_id == "OPP-1001")
    requester = next(item for item in source.permissions() if item.user_id == "USR-5001")
    decision = authorize(opportunity, requester)

    results = retriever.retrieve(
        RetrievalRequest(
            query="buyer deployment urgency dashboard",
            opportunity_id="OPP-1001",
            allowed_source_types=decision.allowed_source_types,
            allowed_access_levels=decision.allowed_access_levels,
        ),
        decision,
    )

    assert results
    assert all(item.opportunity_id in {"OPP-1001", "*"} for item in results)
