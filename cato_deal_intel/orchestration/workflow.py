import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Literal, cast

from qdrant_client import QdrantClient

from ..llm.protocols import LLMProvider
from ..models import RecommendedAction, WorkflowResult
from ..observability.tracing import AgentTraceCollector
from ..retrieval.embeddings import EmbeddingProvider, HashEmbeddingProvider
from ..retrieval.sources.data import SourceData
from ..storage.artifact_store import ArtifactStore
from ..storage.paths import QDRANT_PATH
from .graph import DealState, build_deal_graph

DEAL_GRAPH = build_deal_graph()


def create_brief(
    *,
    root: Path,
    source: SourceData | None = None,
    artifacts_root: Path,
    opportunity_id: str,
    user_id: str,
    llm: LLMProvider,
    approval_decision: Literal["ask", "approved", "rejected", "pending"] = "pending",
    approval_prompt: (
        Callable[[list[RecommendedAction]], Literal["approved", "rejected"]] | None
    ) = None,
    qdrant_path: Path | None = None,
    qdrant_client: QdrantClient | None = None,
    qdrant_client_factory: Callable[[], QdrantClient] | None = None,
    embedding_provider: EmbeddingProvider | None = None,
) -> WorkflowResult:
    """Run the LangGraph flow and return either a brief or a safe denial."""
    initial_state: DealState = {
        "root": root,
        "source": source if source is not None else SourceData(root),
        "artifacts_root": artifacts_root,
        "opportunity_id": opportunity_id,
        "user_id": user_id,
        "llm": llm,
        "approval_decision": approval_decision,
        "run_id": uuid.uuid4().hex,
        "trace_collector": AgentTraceCollector(),
        "qdrant_path": qdrant_path if qdrant_path is not None else QDRANT_PATH,
        "embedding_provider": (
            embedding_provider
            if embedding_provider is not None
            else HashEmbeddingProvider()
        ),
    }
    if approval_prompt is not None:
        initial_state["approval_prompt"] = approval_prompt
    if qdrant_client is not None:
        initial_state["qdrant_client"] = qdrant_client
    if qdrant_client_factory is not None:
        initial_state["qdrant_client_factory"] = qdrant_client_factory
    try:
        result = DEAL_GRAPH.invoke(initial_state)
    except Exception as error:
        traces = initial_state["trace_collector"].traces
        if traces:
            ArtifactStore(artifacts_root).save_failure_trace(
                run_id=initial_state["run_id"],
                opportunity_id=opportunity_id,
                user_id=user_id,
                traces=traces,
                error=error,
            )
        raise
    return cast(WorkflowResult, result.get("brief") or result["denial"])
