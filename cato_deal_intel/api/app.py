"""FastAPI application assembly for the reusable deal-intelligence workflow."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routes.approvals import router as approvals_router
from .routes.briefs import router as briefs_router
from .routes.workflow_runs import router as workflow_runs_router
from .schemas import HealthResponse

app = FastAPI(
    title="Strategic Deal Intelligence API",
    summary="Generate permission-aware, evidence-grounded deal briefs.",
    description=(
        "Demo API for the Strategic Deal Intelligence Assistant. Use **Try it out** on `POST "
        "`/brief` to run the same workflow as the CLI. An authorized request returns a deal "
        "brief; an unauthorized request returns a safe denial. `user_id` is a synthetic demo "
        "identity and is not authenticated by this local prototype. Approval decisions use a "
        "separate endpoint and are restricted to the Deal Desk Approver role. The API does not "
        "write to Salesforce, Slack, or another system of record. Requests use the configured "
        "model; set `CATO_FAKE_LLM=1` for deterministic, no-provider-call demo responses."
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    openapi_tags=[
        {"name": "Demo", "description": "Generate a synthetic deal brief."},
        {"name": "System", "description": "Check local API availability."},
        {"name": "Runs", "description": "Inspect run usage and pending approvals."},
    ],
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)
app.include_router(briefs_router)
app.include_router(approvals_router)
app.include_router(workflow_runs_router)


@app.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Confirms that the local API process is available.",
    tags=["System"],
)
def health() -> HealthResponse:
    """Confirm that the local API process is ready to receive requests."""
    return HealthResponse()


def main() -> None:
    """Start the local HTTP server."""
    import uvicorn

    uvicorn.run("cato_deal_intel.api.app:app", host="127.0.0.1", port=8000, reload=False)


if __name__ == "__main__":
    main()
