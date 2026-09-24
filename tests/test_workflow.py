import json
from pathlib import Path

from cato_deal_intel.llm import FakeLLM
from cato_deal_intel.models import Brief
from cato_deal_intel.workflow import create_brief

ROOT = Path(__file__).parents[1] / "synthetic_data"


def test_fake_workflow_persists_required_brief_artifacts(tmp_path: Path) -> None:
    brief = create_brief(
        root=ROOT,
        artifacts_root=tmp_path,
        opportunity_id="OPP-1001",
        user_id="USR-5001",
        llm=FakeLLM(),
    )
    assert isinstance(brief, Brief)
    run_dir = tmp_path / brief.run_id

    assert brief.source_evidence
    assert any(item.source_type == "slack" for item in brief.source_evidence)
    markdown = (run_dir / "brief.md").read_text()
    assert all(
        section in markdown for section in ["Deal Snapshot", "Executive Summary", "Source Evidence"]
    )
    assert json.loads((run_dir / "brief.json").read_text())["opportunity_id"] == "OPP-1001"


def test_restricted_workflow_routes_approval(tmp_path: Path) -> None:
    brief = create_brief(
        root=ROOT,
        artifacts_root=tmp_path,
        opportunity_id="OPP-1003",
        user_id="USR-5003",
        llm=FakeLLM(),
    )

    assert any("Approval required" in warning for warning in brief.confidence_and_review_warnings)


def test_denied_workflow_does_not_create_artifact(tmp_path: Path) -> None:
    result = create_brief(
        root=ROOT,
        artifacts_root=tmp_path,
        opportunity_id="OPP-1003",
        user_id="USR-5007",
        llm=FakeLLM(),
    )

    assert result.status == "denied"
    assert result.message == "Requester is not authorized for this request."
    assert not list(tmp_path.iterdir())
