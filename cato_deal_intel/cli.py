import json
from pathlib import Path
from typing import Literal

import typer

from .data import SourceData
from .embeddings import configured_embedding_provider
from .llm import configured_llm
from .models import Brief, CostSummary, RecommendedAction
from .retrieval import DEFAULT_QDRANT_PATH, EvidenceRetriever, RetrievalRequest
from .workflow import create_brief

app = typer.Typer(help="Create grounded, permission-aware deal intelligence briefs.")
DATA_ROOT = Path("synthetic_data")
ARTIFACT_ROOT = Path("artifacts/runs")


@app.command()
def ingest() -> None:
    """Load all supplied and synthetic evidence into a local Qdrant collection."""
    source = SourceData(DATA_ROOT)
    retriever = EvidenceRetriever(
        path=DEFAULT_QDRANT_PATH,
        embedding_provider=configured_embedding_provider(),
    )
    evidence = source.evidence()
    retriever.rebuild(evidence)
    typer.echo(f"Indexed {len(evidence)} evidence items into {DEFAULT_QDRANT_PATH}.")


@app.command()
def search(
    opportunity: str = typer.Option(..., "--opportunity"),
    user: str = typer.Option(..., "--user"),
    query: str = typer.Option(..., "--query"),
) -> None:
    """Search only evidence authorized for the requester."""
    source = SourceData(DATA_ROOT)
    opportunity_record = next(
        item for item in source.opportunities() if item.opportunity_id == opportunity
    )
    requester = next((item for item in source.permissions() if item.user_id == user), None)
    from .authorization import authorize

    decision = authorize(opportunity_record, requester)
    retriever = EvidenceRetriever(
        path=DEFAULT_QDRANT_PATH,
        require_existing=True,
        embedding_provider=configured_embedding_provider(),
    )
    results = retriever.retrieve(
        RetrievalRequest(
            query, opportunity, decision.allowed_source_types, decision.allowed_access_levels
        ),
        decision,
    )
    for item in results:
        typer.echo(f"{item.evidence_id} | {item.source_file} | {item.text}")


@app.command()
def brief(
    opportunity: str = typer.Option(..., "--opportunity"),
    user: str = typer.Option(..., "--user"),
    approve: Literal["ask", "approved", "rejected", "pending"] = typer.Option(
        "ask", "--approval", help="ask, approved, rejected, or pending"
    ),
) -> None:
    """Run the four-agent workflow and save JSON and Markdown artifacts."""
    result = create_brief(
        root=DATA_ROOT,
        artifacts_root=ARTIFACT_ROOT,
        opportunity_id=opportunity,
        user_id=user,
        llm=configured_llm(),
        approval_decision=approve,
        approval_prompt=prompt_for_approval,
        embedding_provider=configured_embedding_provider(),
    )
    if isinstance(result, Brief):
        typer.echo(f"Saved run {result.run_id} to {ARTIFACT_ROOT / result.run_id}")
        echo_cost_summary(result.cost_summary)
        return
    typer.echo(f"Request denied: {result.message}")


@app.command()
def usage(run_id: str = typer.Option(..., "--run-id")) -> None:
    """Show token usage and remaining budget for a completed run."""
    path = ARTIFACT_ROOT / run_id / "brief.json"
    if not path.exists():
        raise typer.BadParameter(f"Run was not found: {run_id}")
    brief = Brief.model_validate(json.loads(path.read_text(encoding="utf-8")))
    echo_cost_summary(brief.cost_summary)


def echo_cost_summary(summary: CostSummary) -> None:
    budget = "unlimited" if summary.budget_usd is None else f"${summary.budget_usd:.4f}"
    remaining = "unlimited" if summary.remaining_usd is None else f"${summary.remaining_usd:.4f}"
    typer.echo(
        f"LLM usage: spent=${summary.spent_usd:.4f}; budget={budget}; "
        f"remaining={remaining}; tokens={summary.prompt_tokens + summary.completion_tokens}; "
        f"calls={summary.call_count}"
    )


def prompt_for_approval(actions: list[RecommendedAction]) -> Literal["approved", "rejected"]:
    """Ask for human approval without coupling the workflow to a terminal."""
    typer.echo("\nRecommended actions requiring review:")
    for index, action in enumerate(actions, start=1):
        typer.echo(f"{index}. {action.action} ({action.owner})")
        typer.echo(f"   Rationale: {action.rationale}")
    approved = typer.confirm("Approve these recommendations?")
    return "approved" if approved else "rejected"


@app.command()
def demo() -> None:
    """Run the authorized offline demo; use OPENAI_API_KEY for live calls."""
    import os

    os.environ.setdefault("CATO_FAKE_LLM", "1")
    scenarios = [("OPP-1001", "USR-5001"), ("OPP-1003", "USR-5003")]
    for opportunity, user in scenarios:
        result = create_brief(
            root=DATA_ROOT,
            artifacts_root=ARTIFACT_ROOT,
            opportunity_id=opportunity,
            user_id=user,
            llm=configured_llm(),
            approval_decision="pending",
        )
        if isinstance(result, Brief):
            typer.echo(
                f"{opportunity}: run {result.run_id}; "
                f"approval warnings={len(result.confidence_and_review_warnings)}"
            )
            continue
        typer.echo(f"{opportunity} denied: {result.message}")
    denied = create_brief(
        root=DATA_ROOT,
        artifacts_root=ARTIFACT_ROOT,
        opportunity_id="OPP-1003",
        user_id="USR-5007",
        llm=configured_llm(),
    )
    if not isinstance(denied, Brief):
        typer.echo(f"OPP-1003 denied: {denied.message}")


if __name__ == "__main__":
    app()
