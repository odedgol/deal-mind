import hashlib
import os
import re
from dataclasses import dataclass
from pathlib import Path

from qdrant_client import QdrantClient, models

from .models import AuthorizationDecision, EvidenceItem

COLLECTION_NAME = "deal_evidence"
DEFAULT_QDRANT_PATH = Path(os.getenv("CATO_QDRANT_PATH", "artifacts/qdrant"))


@dataclass(frozen=True)
class RetrievalRequest:
    query: str
    opportunity_id: str
    allowed_source_types: set[str]
    allowed_access_levels: set[str]
    limit: int = 8


class EvidenceRetriever:
    """Indexes evidence once and applies authorization inside every Qdrant query."""

    def __init__(
        self,
        client: QdrantClient | None = None,
        *,
        path: Path | None = None,
        require_existing: bool = False,
    ) -> None:
        self.client = client or (QdrantClient(path=str(path)) if path else QdrantClient(":memory:"))
        self._ensure_collection(require_existing=require_existing)

    def index(self, evidence: list[EvidenceItem]) -> None:
        points = [
            models.PointStruct(
                id=_point_id(item.evidence_id),
                vector=[1.0],
                payload=item.model_dump(mode="json"),
            )
            for item in evidence
        ]
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
        if not decision.allowed:
            return []
        query_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="opportunity_id",
                    match=models.MatchAny(any=[request.opportunity_id, "*"]),
                ),
                models.FieldCondition(
                    key="source_type",
                    match=models.MatchAny(any=sorted(decision.allowed_source_types)),
                ),
                models.FieldCondition(
                    key="access_level",
                    match=models.MatchAny(any=sorted(decision.allowed_access_levels)),
                ),
            ]
        )
        points, _ = self.client.scroll(
            collection_name=COLLECTION_NAME,
            scroll_filter=query_filter,
            limit=max(request.limit * 4, request.limit),
            with_payload=True,
            with_vectors=False,
        )
        ranked = sorted(
            (_to_evidence(point.payload or {}) for point in points),
            key=lambda item: _score(request.query, item.text),
            reverse=True,
        )
        return ranked[: request.limit]

    def _ensure_collection(self, *, require_existing: bool = False) -> None:
        if not self.client.collection_exists(COLLECTION_NAME):
            if require_existing:
                raise RuntimeError("Qdrant index not found. Run `uv run deal-intel ingest` first.")
            self.client.create_collection(
                collection_name=COLLECTION_NAME,
                vectors_config=models.VectorParams(size=1, distance=models.Distance.COSINE),
            )


def _to_evidence(payload: dict[str, object]) -> EvidenceItem:
    return EvidenceItem.model_validate(payload)


def _point_id(evidence_id: str) -> int:
    return int(hashlib.sha256(evidence_id.encode()).hexdigest()[:15], 16)


def _score(query: str, text: str) -> int:
    query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
    text_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
    return len(query_terms & text_terms)
