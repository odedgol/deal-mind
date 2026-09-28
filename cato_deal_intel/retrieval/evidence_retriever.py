"""Authorized hybrid retrieval and evidence index management."""

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from math import exp
from pathlib import Path

from qdrant_client import QdrantClient, models

from ..models import AuthorizationDecision, EvidenceItem, RetrievalDebug
from ..storage.paths import QDRANT_PATH
from .embeddings import EmbeddingProvider, HashEmbeddingProvider

COLLECTION_NAME = "deal_evidence"
DEFAULT_QDRANT_PATH = QDRANT_PATH
RECENCY_HALF_LIFE_DAYS = 180
SOURCE_RELIABILITY = {
    "policies": 0.98,
    "salesforce": 0.95,
    "pricing": 0.92,
    "gong": 0.85,
    "slack": 0.72,
}


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    opportunity_id: str
    allowed_source_types: set[str]
    allowed_access_levels: set[str]
    limit: int = 8
    as_of_date: date | None = None
    shared_policy_only: bool = False


class EvidenceRetriever:
    """Indexes evidence once and applies authorization inside every Qdrant query."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        *,
        path: Path | None = None,
        require_existing: bool = False,
        embedding_provider: EmbeddingProvider | None = None,
    ) -> None:
        self.client = client or (QdrantClient(path=str(path)) if path else QdrantClient(":memory:"))
        self.embedding_provider = embedding_provider or HashEmbeddingProvider()
        self._ensure_collection(require_existing=require_existing)

    def index(self, evidence: list[EvidenceItem]) -> None:
        # Go over the evidence and create embeddings
        embeddings = self.embedding_provider.embed([item.text for item in evidence])
        # Create Qdrant points with the embeddings and the evidence payload
        points = [
            models.PointStruct(
                id=_point_id(item.evidence_id),
                vector=embedding,
                payload=item.model_dump(mode="json"),
            )
            for item, embedding in zip(evidence, embeddings, strict=True)
        ]
        # Upsert the points into the Qdrant collection
        if points:
            self.client.upsert(collection_name=COLLECTION_NAME, points=points)

    def rebuild(self, evidence: list[EvidenceItem]) -> None:
        """Replace the local index with the current source evidence."""
        if self.client.collection_exists(COLLECTION_NAME):
            self.client.delete_collection(COLLECTION_NAME)
        self._ensure_collection()
        self.index(evidence)

    def retrieve(
        self,
        request: RetrievalRequest,
        decision: AuthorizationDecision,
    ) -> list[EvidenceItem]:
        results, _ = self.retrieve_with_debug(request, decision)
        return results

    def retrieve_with_debug(
        self,
        request: RetrievalRequest,
        decision: AuthorizationDecision,
    ) -> tuple[list[EvidenceItem], RetrievalDebug]:
        account_id = _authorized_account_id(request, decision)
        if account_id is None:
            return [], _empty_debug(request, decision)

        # Shared policy is an explicit scope, not a wildcard opportunity query.
        indexed_opportunity_id = "*" if request.shared_policy_only else request.opportunity_id
        allowed_source_types = (
            {"policies"} if request.shared_policy_only else decision.allowed_source_types
        )
        required_filters: list[models.Condition] = [
            models.FieldCondition(
                key="opportunity_id",
                match=models.MatchValue(value=indexed_opportunity_id),
            ),
            models.FieldCondition(
                key="source_type",
                match=models.MatchAny(any=sorted(allowed_source_types)),
            ),
            models.FieldCondition(
                key="access_level",
                match=models.MatchAny(any=sorted(decision.allowed_access_levels)),
            ),
        ]
        if not request.shared_policy_only:
            required_filters.append(
                models.FieldCondition(
                    key="account_id",
                    match=models.MatchValue(value=account_id),
                )
            )
        query_filter = models.Filter(must=required_filters)
        authorized_candidates = self.client.count(
            collection_name=COLLECTION_NAME,
            count_filter=query_filter,
            exact=True,
        ).count
        query_embedding = self.embedding_provider.embed([request.query])[0]
        response = self.client.query_points(
            collection_name=COLLECTION_NAME,
            query=query_embedding,
            query_filter=query_filter,
            limit=max(request.limit * 8, 64),
            with_payload=True,
        )
        candidates = [
            (_to_evidence(point.payload or {}), float(point.score)) for point in response.points
        ]
        bm25_scores = {
            item.evidence_id: _bm25_score(request.query, item.text, candidates)
            for item, _ in candidates
        }
        dense_scores = {item.evidence_id: score for item, score in candidates}
        bm25_rank = _rank_ids(bm25_scores)
        dense_rank = _rank_ids(dense_scores)
        ranked = sorted(
            candidates,
            key=lambda candidate: self._ranking_score(
                candidate[0],
                _rrf_score(candidate[0].evidence_id, bm25_rank, dense_rank),
                request.as_of_date or date.today(),
            ),
            reverse=True,
        )
        results = [item for item, _ in ranked[: request.limit]]
        debug = RetrievalDebug(
            query=request.query,
            opportunity_id=request.opportunity_id,
            authorized_candidates=authorized_candidates,
            dense_candidates=len(candidates),
            final_results=len(results),
            final_evidence_ids=[item.evidence_id for item in results],
            allowed_source_types=sorted(decision.allowed_source_types),
        )
        return results, debug

    @staticmethod
    def _ranking_score(item: EvidenceItem, hybrid_score: float, as_of_date: date) -> float:
        """Blend retrieval relevance with freshness and source trust."""
        freshness = _recency_score(item.event_date, as_of_date)
        reliability = _source_reliability(item)
        return hybrid_score * (0.7 + 0.3 * freshness) * (0.7 + 0.3 * reliability)

    def _ensure_collection(self, *, require_existing: bool = False) -> None:
        if not self.client.collection_exists(COLLECTION_NAME):
            if require_existing:
                raise RuntimeError("Qdrant index not found. Run `uv run deal-intel ingest` first.")
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(
                    size=self.embedding_provider.dimensions,
                    distance=models.Distance.COSINE,
                ),
            )


def _to_evidence(payload: dict[str, object]) -> EvidenceItem:
    return EvidenceItem.model_validate(payload)


def _authorized_account_id(
    request: RetrievalRequest,
    decision: AuthorizationDecision,
) -> str | None:
    if not decision.allowed or request.opportunity_id != decision.opportunity_id:
        return None
    if not decision.account_id:
        return None
    if request.shared_policy_only and "policies" not in decision.allowed_source_types:
        return None
    return decision.account_id


def _empty_debug(
    request: RetrievalRequest,
    decision: AuthorizationDecision,
) -> RetrievalDebug:
    return RetrievalDebug(
        query=request.query,
        opportunity_id=request.opportunity_id,
        authorized_candidates=0,
        dense_candidates=0,
        final_results=0,
        allowed_source_types=sorted(decision.allowed_source_types),
    )


def _point_id(evidence_id: str) -> int:
    return int(hashlib.sha256(evidence_id.encode()).hexdigest()[:15], 16)


def _bm25_score(
    query: str,
    text: str,
    candidates: list[tuple[EvidenceItem, float]],
) -> float:
    documents = [_tokens(item.text) for item, _ in candidates]
    query_terms = _tokens(query)
    current = _tokens(text)
    average_length = sum(len(document) for document in documents) / max(len(documents), 1)
    document_frequency = {
        term: sum(term in document for document in documents) for term in query_terms
    }
    score = 0.0
    for term in query_terms:
        if term not in current:
            continue
        term_frequency = current.count(term)
        inverse_frequency = _idf(len(documents), document_frequency[term])
        denominator = term_frequency + 1.5 * (
            1 - 0.75 + 0.75 * len(current) / max(average_length, 1)
        )
        score += inverse_frequency * (term_frequency * 2.5 / denominator)
    return score


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def _idf(document_count: int, matching_documents: int) -> float:
    return max(0.0, (document_count - matching_documents + 0.5) / (matching_documents + 0.5))


def _rank_ids(scores: dict[str, float]) -> dict[str, int]:
    ranked = sorted(scores, key=lambda evidence_id: scores[evidence_id], reverse=True)
    return {evidence_id: rank for rank, evidence_id in enumerate(ranked, start=1)}


def _rrf_score(evidence_id: str, *rankings: dict[str, int]) -> float:
    return sum(1 / (60 + ranking[evidence_id]) for ranking in rankings)


def _recency_score(event_date: date | None, as_of_date: date) -> float:
    """Apply exponential decay while keeping undated evidence retrievable."""
    if event_date is None:
        return 0.5
    age_days = max(0, (as_of_date - event_date).days)
    return exp(-0.69314718056 * age_days / RECENCY_HALF_LIFE_DAYS)


def _source_reliability(item: EvidenceItem) -> float:
    """Return an explicit source score, falling back to the source-type policy."""
    configured_score = item.metadata.get("source_reliability")
    if configured_score is not None:
        try:
            return min(1.0, max(0.0, float(configured_score)))
        except ValueError:
            pass
    return SOURCE_RELIABILITY.get(item.source_type, 0.5)
