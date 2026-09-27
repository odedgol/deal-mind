import importlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cato_deal_intel.llm.fake_provider import FakeLLMProvider
from cato_deal_intel.retrieval.index import EvidenceRetriever
from cato_deal_intel.retrieval.sources.data import SourceData
from cato_deal_intel.storage.approval_store import ApprovalStore
from cato_deal_intel.storage.client_factory import QdrantClientFactory

api = importlib.import_module("cato_deal_intel.api.app")
deps = importlib.import_module("cato_deal_intel.api.dependencies")
brief_routes = importlib.import_module("cato_deal_intel.api.routes.briefs")


@pytest.fixture
def e2e_client(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> TestClient:
    qdrant_path = tmp_path / "qdrant"
    EvidenceRetriever(path=qdrant_path).index(SourceData(deps.DATA_ROOT).evidence())
    monkeypatch.setattr(deps, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(deps, "APPROVAL_STORE", ApprovalStore(tmp_path))
    monkeypatch.setattr(brief_routes, "configured_llm", lambda: FakeLLMProvider())
    monkeypatch.setattr(brief_routes, "configured_embedding_provider", lambda: None)
    monkeypatch.setattr(deps, "DEFAULT_QDRANT_PATH", qdrant_path)
    monkeypatch.setattr(deps, "QDRANT_CLIENTS", QdrantClientFactory(qdrant_path))
    return TestClient(api.app)


@pytest.mark.e2e
def test_complete_authorization_and_approval_journey(e2e_client: TestClient) -> None:
    unauthorized = e2e_client.post(
        "/brief",
        json={"opportunity_id": "OPP-1003", "user_id": "USR-5007"},
    )
    assert unauthorized.status_code == 200
    assert unauthorized.json()["status"] == "denied"

    generated = e2e_client.post(
        "/brief",
        json={"opportunity_id": "OPP-1003", "user_id": "USR-5003"},
    )
    assert generated.status_code == 200
    pending_brief = generated.json()
    assert pending_brief["run_status"] == "awaiting_approval"
    run_id = pending_brief["run_id"]

    requester_inbox = e2e_client.get(
        "/approvals/inbox", params={"user_id": "USR-5003"}
    )
    assert requester_inbox.status_code == 200
    assert requester_inbox.json() == []

    reviewer_inbox = e2e_client.get(
        "/approvals/inbox", params={"user_id": "USR-5005"}
    )
    assert reviewer_inbox.status_code == 200
    assert reviewer_inbox.json()[0]["approval_request"]["run_id"] == run_id

    decision = e2e_client.post(
        f"/approvals/{run_id}/decision",
        json={"reviewer_user_id": "USR-5005", "decision": "approved"},
    )
    assert decision.status_code == 200
    assert decision.json()["brief"]["run_status"] == "completed"

    restored = e2e_client.get(
        "/runs/requests", params={"user_id": "USR-5003"}
    )
    assert restored.status_code == 200
    assert restored.json()[0]["run_id"] == run_id
    assert restored.json()[0]["run_status"] == "completed"
