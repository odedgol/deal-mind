from datetime import date
from pathlib import Path

from cato_deal_intel.models import EvidenceItem
from cato_deal_intel.retrieval.evidence_retriever import (
    EvidenceRetriever,
    RetrievalRequest,
    _recency_score,
    _source_reliability,
)
from cato_deal_intel.retrieval.sources.data import SourceData
from cato_deal_intel.security.authorization import authorize

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
    assert all(item.opportunity_id == "OPP-1003" for item in results)
    assert all(item.access_level in {"standard", "sensitive", "restricted"} for item in results)


def test_opportunity_evidence_has_account_scope(tmp_path: Path) -> None:
    source, _ = _retriever(tmp_path)

    opportunity_evidence = [item for item in source.evidence() if item.opportunity_id != "*"]

    assert opportunity_evidence
    assert all(item.account_id is not None for item in opportunity_evidence)


def test_retrieval_rejects_evidence_with_mismatched_account(tmp_path: Path) -> None:
    source, retriever = _retriever(tmp_path)
    opportunity = source.opportunity("OPP-1001")
    requester = source.permission_profile("USR-5001")
    assert opportunity is not None
    decision = authorize(opportunity, requester)
    mismatched = EvidenceItem(
        evidence_id="test:wrong-account",
        opportunity_id="OPP-1001",
        account_id="ACC-OTHER",
        source_type="gong",
        source_file="test",
        source_id="wrong-account",
        access_level="standard",
        text="buyer deployment urgency dashboard",
    )
    retriever.index([mismatched])

    results = retriever.retrieve(
        RetrievalRequest(
            query="buyer deployment urgency dashboard",
            opportunity_id="OPP-1001",
            allowed_source_types=decision.allowed_source_types,
            allowed_access_levels=decision.allowed_access_levels,
        ),
        decision,
    )

    assert all(item.evidence_id != mismatched.evidence_id for item in results)


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
    assert all(item.opportunity_id == "OPP-1001" for item in results)


def test_recency_score_prefers_recent_evidence() -> None:
    as_of = date(2026, 6, 1)

    recent = _recency_score(date(2026, 5, 25), as_of)
    old = _recency_score(date(2025, 5, 25), as_of)

    assert recent > old
    assert 0 < old < 1


def test_source_reliability_supports_policy_override() -> None:
    item = EvidenceItem(
        evidence_id="test:1",
        opportunity_id="OPP-1001",
        source_type="slack",
        source_file="test",
        source_id="1",
        access_level="standard",
        text="test",
        metadata={"source_reliability": "0.91"},
    )

    assert _source_reliability(item) == 0.91
