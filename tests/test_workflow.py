import json
from pathlib import Path

import pytest

from cato_deal_intel.data import SourceData
from cato_deal_intel.llm import FakeLLM
from cato_deal_intel.models import Brief
from cato_deal_intel.retrieval import EvidenceRetriever
from cato_deal_intel.workflow import create_brief

ROOT = Path(__file__).parents[1] / "synthetic_data"


def _prepare_index(path: Path) -> Path:
    qdrant_path = path / "qdrant"
    EvidenceRetriever(path=qdrant_path).index(SourceData(ROOT).evidence())
    return qdrant_path


def test_fake_workflow_persists_required_brief_artifacts(tmp_path: Path) -> None:
    qdrant_path = _prepare_index(tmp_path)
    brief = create_brief(
        root=ROOT,
        artifacts_root=tmp_path,
        opportunity_id="OPP-1001",
        user_id="USR-5001",
        llm=FakeLLM(),
        qdrant_path=qdrant_path,
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
    traces = json.loads((run_dir / "trace.json").read_text())
    assert {trace["agent_name"] for trace in traces} == {
        "Deal Context Agent",
        "Conversation Intelligence Agent",
        "Stakeholder Map Agent",
        "Negotiation Strategy Agent",
    }
    assert all(trace["status"] == "completed" for trace in traces)
    assert all(trace["run_id"] == brief.run_id for trace in traces)


def test_restricted_workflow_routes_approval(tmp_path: Path) -> None:
    qdrant_path = _prepare_index(tmp_path)
    brief = create_brief(
        root=ROOT,
        artifacts_root=tmp_path,
        opportunity_id="OPP-1003",
        user_id="USR-5003",
        llm=FakeLLM(),
        qdrant_path=qdrant_path,
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


def test_failed_agent_persists_failed_trace(tmp_path: Path) -> None:
    qdrant_path = _prepare_index(tmp_path)

    class FailingLLM:
        def complete(self, **_: object) -> object:
            raise RuntimeError("simulated agent failure")

    with pytest.raises(RuntimeError, match="simulated agent failure"):
        create_brief(
            root=ROOT,
            artifacts_root=tmp_path,
            opportunity_id="OPP-1001",
            user_id="USR-5001",
            llm=FailingLLM(),  # type: ignore[arg-type]
            qdrant_path=qdrant_path,
        )

    run_dir = next(path for path in tmp_path.iterdir() if path.name != "qdrant")
    traces = json.loads((run_dir / "trace.json").read_text())
    assert any(trace["status"] == "failed" for trace in traces)
    assert (run_dir / "error.json").exists()
    assert not (run_dir / "brief.json").exists()
