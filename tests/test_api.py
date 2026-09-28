import json
from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cato_deal_intel.llm.fake_provider import FakeLLMProvider
from cato_deal_intel.orchestration.services import ApprovalRequestService, RunArtifactService
from cato_deal_intel.retrieval.evidence_retriever import EvidenceRetriever
from cato_deal_intel.retrieval.sources.data import SourceData
from cato_deal_intel.storage.approval_store import ApprovalStore
from cato_deal_intel.storage.artifact_store import ArtifactStore
from cato_deal_intel.storage.client_factory import QdrantClientFactory

api = import_module("cato_deal_intel.api.app")
deps = import_module("cato_deal_intel.api.dependencies")
brief_routes = import_module("cato_deal_intel.api.routes.briefs")


def test_health_endpoint() -> None:
    response = TestClient(api.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_swagger_ui_and_openapi_include_demo_scenarios() -> None:
    client = TestClient(api.app)

    docs = client.get("/docs")
    schema = client.get("/openapi.json").json()

    assert docs.status_code == 200
    assert "swagger-ui" in docs.text
    assert {
        "/health",
        "/brief",
        "/runs/{run_id}/usage",
        "/runs/requests",
        "/approvals/inbox",
        "/approvals/inbox/count",
        "/approvals/{run_id}/decision",
    } <= set(schema["paths"])
    examples = schema["components"]["schemas"]["BriefRequest"]["examples"]
    assert [example["user_id"] for example in examples] == [
        "USR-5001",
        "USR-5003",
        "USR-5007",
    ]


def test_api_reuses_one_local_qdrant_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(deps, "QDRANT_CLIENTS", QdrantClientFactory(tmp_path / "qdrant"))

    first = deps.QDRANT_CLIENTS()
    second = deps.QDRANT_CLIENTS()

    assert first is second


def test_brief_endpoint_reuses_workflow(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    qdrant_path = tmp_path / "qdrant"
    evidence_repository = EvidenceRetriever(path=qdrant_path)
    evidence_repository.index(SourceData(deps.SOURCE_DATA_ROOT).evidence())
    monkeypatch.setattr(deps, "ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(
        deps, "RUN_ARTIFACT_SERVICE", RunArtifactService(ArtifactStore(tmp_path))
    )
    monkeypatch.setattr(deps, "APPROVAL_SERVICE", ApprovalRequestService(ApprovalStore(tmp_path)))
    monkeypatch.setattr(brief_routes, "configured_llm", lambda: FakeLLMProvider())
    monkeypatch.setattr(deps, "DEFAULT_QDRANT_PATH", qdrant_path)
    monkeypatch.setattr(deps, "QDRANT_CLIENTS", QdrantClientFactory(qdrant_path))
    monkeypatch.setattr(deps, "EVIDENCE_REPOSITORY", evidence_repository)

    response = TestClient(api.app).post(
        "/brief",
        json={
            "opportunity_id": "OPP-1001",
            "user_id": "USR-5001",
        },
    )

    assert response.status_code == 200
    assert response.json()["opportunity_id"] == "OPP-1001"
    assert response.json()["run_status"] == "completed"
    run_id = response.json()["run_id"]
    usage_response = TestClient(api.app).get(f"/runs/{run_id}/usage")
    assert usage_response.status_code == 200
    assert usage_response.json()["run_spent_usd"] is not None


def test_authorized_read_requests_can_run_concurrently(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    qdrant_path = tmp_path / "qdrant"
    evidence_repository = EvidenceRetriever(path=qdrant_path)
    evidence_repository.index(SourceData(deps.SOURCE_DATA_ROOT).evidence())
    monkeypatch.setattr(deps, "ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(
        deps, "RUN_ARTIFACT_SERVICE", RunArtifactService(ArtifactStore(tmp_path))
    )
    monkeypatch.setattr(deps, "APPROVAL_SERVICE", ApprovalRequestService(ApprovalStore(tmp_path)))
    monkeypatch.setattr(brief_routes, "configured_llm", lambda: FakeLLMProvider())
    monkeypatch.setattr(deps, "DEFAULT_QDRANT_PATH", qdrant_path)
    monkeypatch.setattr(deps, "QDRANT_CLIENTS", QdrantClientFactory(qdrant_path))
    monkeypatch.setattr(deps, "EVIDENCE_REPOSITORY", evidence_repository)
    client = TestClient(api.app)

    def request_brief(_: int) -> tuple[int, str]:
        response = client.post(
            "/brief",
            json={"opportunity_id": "OPP-1001", "user_id": "USR-5001"},
        )
        return response.status_code, response.json()["run_status"]

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(request_brief, range(4)))

    assert results == [(200, "completed")] * 4
    assert len(list(tmp_path.glob("*/brief.json"))) == 4


def test_brief_endpoint_returns_safe_denial() -> None:
    response = TestClient(api.app).post(
        "/brief",
        json={
            "opportunity_id": "OPP-1003",
            "user_id": "USR-5007",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    assert response.json()["message"] == "Requester is not authorized for this request."


@pytest.mark.parametrize(
    ("decision", "expected_run_status"),
    [("approved", "completed"), ("rejected", "rejected")],
)
def test_approval_decision_updates_existing_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, decision: str, expected_run_status: str
) -> None:
    qdrant_path = tmp_path / "qdrant"
    evidence_repository = EvidenceRetriever(path=qdrant_path)
    evidence_repository.index(SourceData(deps.SOURCE_DATA_ROOT).evidence())
    monkeypatch.setattr(deps, "ARTIFACTS_ROOT", tmp_path)
    monkeypatch.setattr(
        deps, "RUN_ARTIFACT_SERVICE", RunArtifactService(ArtifactStore(tmp_path))
    )
    monkeypatch.setattr(deps, "APPROVAL_SERVICE", ApprovalRequestService(ApprovalStore(tmp_path)))
    monkeypatch.setattr(brief_routes, "configured_llm", lambda: FakeLLMProvider())
    monkeypatch.setattr(deps, "DEFAULT_QDRANT_PATH", qdrant_path)
    monkeypatch.setattr(deps, "QDRANT_CLIENTS", QdrantClientFactory(qdrant_path))
    monkeypatch.setattr(deps, "EVIDENCE_REPOSITORY", evidence_repository)
    client = TestClient(api.app)

    generated = client.post("/brief", json={"opportunity_id": "OPP-1003", "user_id": "USR-5003"})
    brief = generated.json()
    run_id = brief["run_id"]
    assert generated.status_code == 200
    assert brief["run_status"] == "awaiting_approval"
    assert "eligible_approver_user_ids" not in brief
    assert client.get("/approvals/inbox", params={"user_id": "USR-5003"}).json() == []
    inbox = client.get("/approvals/inbox", params={"user_id": "USR-5005"}).json()
    assert len(inbox) == 1
    assert client.get("/approvals/inbox/count", params={"user_id": "USR-5005"}).json() == {
        "count": 1
    }
    assert inbox[0]["approval_request"]["requester_user_id"] == "USR-5003"

    unauthorized = client.post(
        f"/approvals/{run_id}/decision",
        json={"reviewer_user_id": "USR-5003", "decision": "approved"},
    )
    assert unauthorized.status_code == 403

    approved = client.post(
        f"/approvals/{run_id}/decision",
        json={"reviewer_user_id": "USR-5005", "decision": decision},
    )
    assert approved.status_code == 200
    assert approved.json()["brief"]["run_id"] == run_id
    assert approved.json()["brief"]["run_status"] == expected_run_status
    requester_runs = client.get("/runs/requests", params={"user_id": "USR-5003"}).json()
    assert len(requester_runs) == 1
    assert requester_runs[0]["run_id"] == run_id
    assert requester_runs[0]["run_status"] == expected_run_status
    assert "reviewer_user_id" not in requester_runs[0]
    assert client.get("/approvals/inbox", params={"user_id": "USR-5005"}).json() == []
    assert client.get("/approvals/inbox/count", params={"user_id": "USR-5005"}).json() == {
        "count": 0
    }
    assert len(list(tmp_path.glob("*/brief.json"))) == 1
    traces = (tmp_path / run_id / "trace.json").read_text()
    assert '"reviewer_user_id": "USR-5005"' in traces
    assert f'"decision": "{decision}"' in traces
    run_dir = tmp_path / run_id
    saved_approvals = json.loads((run_dir / "approval.json").read_text())
    saved_request = json.loads((run_dir / "approval_request.json").read_text())
    saved_brief = json.loads((run_dir / "brief.json").read_text())
    saved_markdown = (run_dir / "brief.md").read_text()
    assert all(record["decision"] == decision for record in saved_approvals)
    assert saved_request["status"] == decision
    assert saved_request["reviewer_user_id"] == "USR-5005"
    assert saved_brief["run_status"] == expected_run_status
    assert f"**Workflow status:** {expected_run_status}" in saved_markdown

    repeated_request = client.post(
        "/brief",
        json={"opportunity_id": "OPP-1003", "user_id": "USR-5003"},
    )
    repeated_run = repeated_request.json()
    assert repeated_request.status_code == 200
    assert repeated_run["run_status"] == "awaiting_approval"
    assert repeated_run["run_id"] != run_id
    assert (
        client.get("/approvals/inbox", params={"user_id": "USR-5005"}).json()[0][
            "approval_request"
        ]["run_id"]
        == repeated_run["run_id"]
    )

    approved_again = client.post(
        f"/approvals/{repeated_run['run_id']}/decision",
        json={"reviewer_user_id": "USR-5005", "decision": "approved"},
    )
    assert approved_again.status_code == 200
    assert approved_again.json()["brief"]["run_id"] == repeated_run["run_id"]
    assert approved_again.json()["brief"]["run_status"] == "completed"


def test_deal_desk_approver_cannot_request_and_approve_own_restricted_deal(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(deps, "ARTIFACTS_ROOT", tmp_path)
    response = TestClient(api.app).post(
        "/brief",
        json={"opportunity_id": "OPP-1003", "user_id": "USR-5005"},
    )

    assert response.status_code == 409
    assert (
        response.json()["detail"]
        == "This approval-required request needs another Deal Desk Approver."
    )
    assert not list(tmp_path.glob("*/brief.json"))


def test_brief_endpoint_rejects_caller_supplied_approval_decision() -> None:
    response = TestClient(api.app).post(
        "/brief",
        json={"opportunity_id": "OPP-1003", "user_id": "USR-5003", "approval_decision": "approved"},
    )

    assert response.status_code == 422
