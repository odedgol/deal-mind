from collections.abc import Callable
from pathlib import Path
from typing import cast

import pytest

from cato_deal_intel.evaluation.runner import (
    _approval_requirement_is_met,
    run_golden_evaluation,
)
from cato_deal_intel.llm.protocols import LLMProvider
from cato_deal_intel.models import RecommendedAction

ROOT = Path(__file__).parents[1]


def test_conservative_extra_approval_does_not_fail_safety_check() -> None:
    action = RecommendedAction(
        action="Consult Legal about an internal clarification.",
        owner="Legal",
        rationale="Resolve open terms before any customer-facing response.",
        evidence_ids=["gong:CALL-001"],
        requires_approval=True,
    )

    assert _approval_requirement_is_met([action], expected=False)
    assert _approval_requirement_is_met([action], expected=True)
    assert not _approval_requirement_is_met(
        [action.model_copy(update={"requires_approval": False})], expected=True
    )


def test_golden_evaluation_passes_synthetic_cases(tmp_path: Path) -> None:
    report = run_golden_evaluation(
        root=ROOT / "synthetic_data",
        qdrant_path=tmp_path / "qdrant",
        artifacts_root=tmp_path / "runs",
        golden_path=ROOT / "evals/scenarios/golden_set.json",
    )

    assert report.total_cases == 4
    assert report.passed_cases == 4
    assert report.pass_rate == 1.0
    assert all(result.checks["citation_ids"] for result in report.results)
    assert all(result.checks["citation_coverage"] for result in report.results)
    assert all(result.checks["unauthorized_leakage"] for result in report.results)


def test_golden_evaluation_repeats_every_case(tmp_path: Path) -> None:
    report = run_golden_evaluation(
        root=ROOT / "synthetic_data",
        qdrant_path=tmp_path / "qdrant",
        artifacts_root=tmp_path / "runs",
        golden_path=ROOT / "evals/scenarios/golden_set.json",
        repeats=3,
    )

    assert report.total_cases == 12
    assert report.passed_cases == 12
    assert {result.repeat for result in report.results} == {1, 2, 3}


def test_golden_evaluation_rejects_zero_repeats(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        run_golden_evaluation(
            root=ROOT / "synthetic_data",
            qdrant_path=tmp_path / "qdrant",
            artifacts_root=tmp_path / "runs",
            golden_path=ROOT / "evals/scenarios/golden_set.json",
            repeats=0,
        )


def test_golden_evaluation_records_model_failures_and_continues(tmp_path: Path) -> None:
    class FailingLLM:
        def complete(self, **_: object) -> object:
            raise ValueError("invalid citation")

    report = run_golden_evaluation(
        root=ROOT / "synthetic_data",
        qdrant_path=tmp_path / "qdrant",
        artifacts_root=tmp_path / "runs",
        golden_path=ROOT / "evals/scenarios/golden_set.json",
        llm_factory=cast(Callable[[], LLMProvider], FailingLLM),
    )

    assert report.total_cases == 4
    assert report.passed_cases == 1
    assert sum(result.error_type == "ValueError" for result in report.results) == 3
