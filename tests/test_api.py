from fastapi.testclient import TestClient

from cato_deal_intel import api
from cato_deal_intel.client_factory import QdrantClientFactory
from cato_deal_intel.data import SourceData
from cato_deal_intel.llm import FakeLLM
from cato_deal_intel.retrieval import EvidenceRetriever


def test_health_endpoint() -> None:
    response = TestClient(api.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_api_reuses_one_local_qdrant_client(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(api, "_qdrant_clients", QdrantClientFactory(tmp_path / "qdrant"))

    first = api._qdrant_clients()
    second = api._qdrant_clients()

    assert first is second


def test_brief_endpoint_reuses_workflow(monkeypatch, tmp_path) -> None:
    qdrant_path = tmp_path / "qdrant"
    EvidenceRetriever(path=qdrant_path).index(SourceData(api.DATA_ROOT).evidence())
    monkeypatch.setattr(api, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(api, "configured_llm", lambda: FakeLLM())
    monkeypatch.setattr(api, "configured_embedding_provider", lambda: None)
    monkeypatch.setattr(api, "DEFAULT_QDRANT_PATH", qdrant_path)
    monkeypatch.setattr(api, "_qdrant_clients", QdrantClientFactory(qdrant_path))

    response = TestClient(api.app).post(
        "/brief",
        json={
            "opportunity_id": "OPP-1001",
            "user_id": "USR-5001",
            "approval_decision": "pending",
        },
    )

    assert response.status_code == 200
    assert response.json()["opportunity_id"] == "OPP-1001"
    run_id = response.json()["run_id"]
    usage_response = TestClient(api.app).get(f"/runs/{run_id}/usage")
    assert usage_response.status_code == 200
    assert usage_response.json()["budget_usd"] is not None


def test_brief_endpoint_returns_safe_denial() -> None:
    response = TestClient(api.app).post(
        "/brief",
        json={
            "opportunity_id": "OPP-1003",
            "user_id": "USR-5007",
            "approval_decision": "pending",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "denied"
    assert response.json()["message"] == "Requester is not authorized for this request."
