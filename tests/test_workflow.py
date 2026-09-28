import json
from pathlib import Path
from typing import Literal

import pytest

from cato_deal_intel.llm.fake_provider import FakeLLMProvider
from cato_deal_intel.models import Brief, RecommendedAction
from cato_deal_intel.orchestration.services import RunArtifactService
from cato_deal_intel.orchestration.workflow import create_brief
from cato_deal_intel.retrieval.evidence_retriever import EvidenceRetriever
from cato_deal_intel.retrieval.sources.data import SourceData
from cato_deal_intel.storage.artifact_store import ArtifactStore

ROOT = Path(__file__).parents[1] / "synthetic_data"


def _prepare_index(path: Path) -> EvidenceRetriever:
    qdrant_path = path / "qdrant"
    retriever = EvidenceRetriever(path=qdrant_path)
    retriever.index(SourceData(ROOT).evidence())
    return retriever


def test_fake_workflow_persists_required_brief_artifacts(tmp_path: Path) -> None:
    evidence_repository = _prepare_index(tmp_path)
    brief = create_brief(
        deal_repository=SourceData(ROOT),
        run_artifact_service=RunArtifactService(ArtifactStore(tmp_path)),
        opportunity_id="OPP-1001",
        user_id="USR-5001",
        llm=FakeLLMProvider(),
        evidence_repository=evidence_repository,
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
    agent_traces = [trace for trace in traces if trace["event_type"] == "agent"]
    assert {trace["name"] for trace in agent_traces} == {
        "Deal Context Agent",
        "Conversation Intelligence Agent",
        "Stakeholder Map Agent",
        "Negotiation Strategy Agent",
    }
    assert {trace["event_type"] for trace in traces} == {
        "agent",
        "retrieval",
        "tool",
        "approval",
        "recommendation",
    }
    assert all(trace["status"] == "completed" for trace in traces)
    assert all(trace["run_id"] == brief.run_id for trace in traces)


def test_restricted_workflow_routes_approval(tmp_path: Path) -> None:
    evidence_repository = _prepare_index(tmp_path)
    brief = create_brief(
        deal_repository=SourceData(ROOT),
        run_artifact_service=RunArtifactService(ArtifactStore(tmp_path)),
        opportunity_id="OPP-1003",
        user_id="USR-5003",
        llm=FakeLLMProvider(),
        evidence_repository=evidence_repository,
    )

    assert isinstance(brief, Brief)
    assert any("Approval required" in warning for warning in brief.confidence_and_review_warnings)


def test_interactive_approval_callback_controls_approval_status(tmp_path: Path) -> None:
    evidence_repository = _prepare_index(tmp_path)
    reviewed: list[list[RecommendedAction]] = []

    def approve(actions: list[RecommendedAction]) -> Literal["approved"]:
        reviewed.append(actions)
        return "approved"

    brief = create_brief(
        deal_repository=SourceData(ROOT),
        run_artifact_service=RunArtifactService(ArtifactStore(tmp_path)),
        opportunity_id="OPP-1003",
        user_id="USR-5003",
        llm=FakeLLMProvider(),
        approval_decision="ask",
        approval_prompt=approve,
        evidence_repository=evidence_repository,
    )

    assert isinstance(brief, Brief)
    assert reviewed and reviewed[0]
    approvals = json.loads((tmp_path / brief.run_id / "approval.json").read_text())
    assert all(record["decision"] == "approved" for record in approvals)


def test_denied_workflow_does_not_create_artifact(tmp_path: Path) -> None:
    result = create_brief(
        deal_repository=SourceData(ROOT),
        run_artifact_service=RunArtifactService(ArtifactStore(tmp_path)),
        evidence_repository=EvidenceRetriever(),
        opportunity_id="OPP-1003",
        user_id="USR-5007",
        llm=FakeLLMProvider(),
    )

    assert not isinstance(result, Brief)
    assert result.status == "denied"
    assert result.message == "Requester is not authorized for this request."
    assert not list(tmp_path.iterdir())


def test_failed_agent_persists_failed_trace(tmp_path: Path) -> None:
    evidence_repository = _prepare_index(tmp_path)

    class FailingLLM:
        def complete(self, **_: object) -> object:
            raise RuntimeError("simulated agent failure")

    with pytest.raises(RuntimeError, match="simulated agent failure"):
        create_brief(
            deal_repository=SourceData(ROOT),
            run_artifact_service=RunArtifactService(ArtifactStore(tmp_path)),
            opportunity_id="OPP-1001",
            user_id="USR-5001",
            llm=FailingLLM(),  # type: ignore[arg-type]
            evidence_repository=evidence_repository,
        )

    run_dir = next(path for path in tmp_path.iterdir() if path.name != "qdrant")
    traces = json.loads((run_dir / "trace.json").read_text())
    assert any(trace["status"] == "failed" for trace in traces)
    assert (run_dir / "error.json").exists()
    assert not (run_dir / "brief.json").exists()
