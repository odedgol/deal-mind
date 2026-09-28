import os
from pathlib import Path
from typing import Literal

import typer

from ..evaluation.runner import run_golden_evaluation, run_quality_evaluation
from ..llm.fake_provider import FakeLLMProvider
from ..llm.providers import OpenAIProvider
from ..llm.settings import configured_llm
from ..models import Brief, CostSummary, RecommendedAction
from ..orchestration.services import DealService, EvidenceServiceFactory, RunArtifactService
from ..orchestration.workflow import create_brief
from ..retrieval.embeddings import configured_embedding_provider
from ..retrieval.evidence_retriever import EvidenceRetriever, RetrievalRequest
from ..retrieval.sources.data import SourceData
from ..security.authorization import authorize
from ..storage.artifact_store import ArtifactStore
from ..storage.paths import QDRANT_PATH, RUN_ARTIFACTS_PATH, SOURCE_DATA_PATH

app = typer.Typer(help="Create grounded, permission-aware deal intelligence briefs.")
SOURCE_DATA_ROOT = SOURCE_DATA_PATH
ARTIFACTS_ROOT = RUN_ARTIFACTS_PATH
RUN_ARTIFACT_SERVICE = RunArtifactService(ArtifactStore(ARTIFACTS_ROOT))
DEFAULT_QDRANT_PATH = QDRANT_PATH
DEAL_REPOSITORY = SourceData(SOURCE_DATA_ROOT)
EVIDENCE_REPOSITORY = EvidenceRetriever(
    path=DEFAULT_QDRANT_PATH,
    require_existing=True,
    embedding_provider=configured_embedding_provider(),
)
DEAL_SERVICE = DealService(DEAL_REPOSITORY)
EVIDENCE_SERVICE_FACTORY = EvidenceServiceFactory(EVIDENCE_REPOSITORY)


@app.command()
def ingest() -> None:
    """Load all supplied and synthetic evidence into a local Qdrant collection."""
    deal_repository = SourceData(SOURCE_DATA_ROOT)
    retriever = EvidenceRetriever(
        path=DEFAULT_QDRANT_PATH,
        embedding_provider=configured_embedding_provider(),
    )
    evidence = deal_repository.evidence()
    retriever.rebuild(evidence)
    typer.echo(f"Indexed {len(evidence)} evidence items into {DEFAULT_QDRANT_PATH}.")


@app.command()
def search(
    opportunity: str = typer.Option(..., "--opportunity"),
    user: str = typer.Option(..., "--user"),
    query: str = typer.Option(..., "--query"),
) -> None:
    """Search only evidence authorized for the requester."""
    deal_repository = SourceData(SOURCE_DATA_ROOT)
    opportunity_record = next(
        item for item in deal_repository.opportunities() if item.opportunity_id == opportunity
    )
    requester = next((item for item in deal_repository.permissions() if item.user_id == user), None)
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
        deal_service=DEAL_SERVICE,
        run_artifact_service=RUN_ARTIFACT_SERVICE,
        evidence_service_factory=EVIDENCE_SERVICE_FACTORY,
        opportunity_id=opportunity,
        user_id=user,
        llm=configured_llm(),
        approval_decision=approve,
        approval_prompt=prompt_for_approval,
    )
    if isinstance(result, Brief):
        typer.echo(f"Saved run {result.run_id} to {ARTIFACTS_ROOT / result.run_id}")
        echo_cost_summary(result.cost_summary)
        return
    typer.echo(f"Request denied: {result.message}")


@app.command()
def usage(run_id: str = typer.Option(..., "--run-id")) -> None:
    """Show token usage and remaining budget for a completed run."""
    brief = RUN_ARTIFACT_SERVICE.find_brief(run_id)
    if brief is None:
        raise typer.BadParameter(f"Run was not found: {run_id}")
    echo_cost_summary(brief.cost_summary)


@app.command()
def evaluate(
    mode: Literal["fake", "live", "both"] = typer.Option(
        "fake", "--mode", help="Run against FakeLLMProvider, OpenAI, or both."
    ),
    repeats: int = typer.Option(
        3, "--repeats", min=1, help="Number of full Golden Set passes for live evaluation."
    ),
    suite: Literal["all", "workflow", "quality"] = typer.Option(
        "all", "--suite", help="Run workflow cases, adversarial quality cases, or both."
    ),
) -> None:
    """Run deterministic and/or repeated live Golden Set evaluations."""
    if mode in {"live", "both"} and not os.getenv("OPENAI_API_KEY"):
        raise typer.BadParameter("Set OPENAI_API_KEY before requesting live evaluation.")

    all_passed = True
    modes = ["fake", "live"] if mode == "both" else [mode]
    for selected_mode in modes:
        factory = FakeLLMProvider if selected_mode == "fake" else OpenAIProvider
        run_count = 1 if selected_mode == "fake" else repeats
        results = []
        if suite in {"all", "workflow"}:
            workflow_report = run_golden_evaluation(
                source_data_root=SOURCE_DATA_ROOT,
                qdrant_path=Path(f"artifacts/eval-qdrant-{selected_mode}"),
                artifacts_root=Path(f"artifacts/evaluations/{selected_mode}"),
                golden_path=Path("evals/scenarios/golden_set.json"),
                llm_factory=factory,
                repeats=run_count,
            )
            results.extend(workflow_report.results)
        if suite in {"all", "quality"}:
            quality_report = run_quality_evaluation(
                scenarios_path=Path("evals/scenarios/quality_scenarios.json"),
                llm_factory=factory,
                repeats=run_count,
            )
            results.extend(quality_report.results)
        passed_cases = sum(result.passed for result in results)
        typer.echo(f"{selected_mode.upper()} evaluation: {passed_cases}/{len(results)} passed")
        for result in results:
            status = "PASS" if result.passed else "FAIL"
            details = f" | details={result.details}" if result.details else ""
            typer.echo(
                f"{status} | run {result.repeat} | {result.name} | "
                f"error={result.error_type or 'none'} | {result.checks}{details}"
            )
        all_passed = all_passed and passed_cases == len(results)
    if not all_passed:
        raise typer.Exit(code=1)


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
            deal_service=DEAL_SERVICE,
            run_artifact_service=RUN_ARTIFACT_SERVICE,
            evidence_service_factory=EVIDENCE_SERVICE_FACTORY,
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
        deal_service=DEAL_SERVICE,
        run_artifact_service=RUN_ARTIFACT_SERVICE,
        evidence_service_factory=EVIDENCE_SERVICE_FACTORY,
        opportunity_id="OPP-1003",
        user_id="USR-5007",
        llm=configured_llm(),
    )
    if not isinstance(denied, Brief):
        typer.echo(f"OPP-1003 denied: {denied.message}")


if __name__ == "__main__":
    app()
