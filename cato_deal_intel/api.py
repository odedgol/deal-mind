"""Small HTTP adapter for the reusable deal-intelligence workflow."""

import json
from pathlib import Path
from threading import Lock
from typing import Literal

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict

from .cli import ARTIFACT_ROOT, DATA_ROOT
from .client_factory import QdrantClientFactory
from .embeddings import configured_embedding_provider
from .llm import configured_llm
from .models import Brief, CostSummary, DeniedResult
from .retrieval import DEFAULT_QDRANT_PATH
from .workflow import create_brief


class BriefRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    opportunity_id: str
    user_id: str
    approval_decision: Literal["approved", "rejected", "pending"] = "pending"


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"


app = FastAPI(title="Deal Intelligence API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
_brief_lock = Lock()
_qdrant_clients = QdrantClientFactory(DEFAULT_QDRANT_PATH)


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Confirm that the local API process is ready to receive requests."""
    return HealthResponse()


@app.post("/brief", response_model=Brief | DeniedResult)
def generate_brief(request: BriefRequest) -> Brief | DeniedResult:
    """Run the same workflow exposed by the CLI and return its result."""
    with _brief_lock:
        return create_brief(
            root=DATA_ROOT,
            artifacts_root=ARTIFACT_ROOT,
            opportunity_id=request.opportunity_id,
            user_id=request.user_id,
            llm=configured_llm(),
            approval_decision=request.approval_decision,
            qdrant_path=DEFAULT_QDRANT_PATH,
            qdrant_client_factory=_qdrant_clients,
            embedding_provider=configured_embedding_provider(),
        )


@app.get("/runs/{run_id}/usage", response_model=CostSummary)
def get_run_usage(run_id: str) -> CostSummary:
    """Return the persisted model usage summary for one completed run."""
    path = Path(ARTIFACT_ROOT) / run_id / "brief.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Run was not found.")
    brief = Brief.model_validate(json.loads(path.read_text(encoding="utf-8")))
    return brief.cost_summary


def main() -> None:
    """Start the local HTTP server."""
    import uvicorn

    uvicorn.run("cato_deal_intel.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
