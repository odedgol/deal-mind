"""Small HTTP adapter for the reusable deal-intelligence workflow."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel, ConfigDict

from .cli import ARTIFACT_ROOT, DATA_ROOT
from .embeddings import configured_embedding_provider
from .llm import configured_llm
from .models import Brief, DeniedResult
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


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Confirm that the local API process is ready to receive requests."""
    return HealthResponse()


@app.post("/brief", response_model=Brief | DeniedResult)
def generate_brief(request: BriefRequest) -> Brief | DeniedResult:
    """Run the same workflow exposed by the CLI and return its result."""
    return create_brief(
        root=DATA_ROOT,
        artifacts_root=ARTIFACT_ROOT,
        opportunity_id=request.opportunity_id,
        user_id=request.user_id,
        llm=configured_llm(),
        approval_decision=request.approval_decision,
        qdrant_path=DEFAULT_QDRANT_PATH,
        embedding_provider=configured_embedding_provider(),
    )


def main() -> None:
    """Start the local HTTP server."""
    import uvicorn

    uvicorn.run("cato_deal_intel.api:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
