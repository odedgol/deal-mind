from pathlib import Path

from cato_deal_intel.evaluation import run_golden_evaluation

ROOT = Path(__file__).parents[1]


def test_golden_evaluation_passes_synthetic_cases(tmp_path: Path) -> None:
    report = run_golden_evaluation(
        root=ROOT / "synthetic_data",
        qdrant_path=tmp_path / "qdrant",
        artifacts_root=tmp_path / "runs",
        golden_path=ROOT / "evals/golden_set.json",
    )

    assert report.total_cases == 4
    assert report.passed_cases == 4
    assert report.pass_rate == 1.0
