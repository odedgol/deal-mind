from fastapi.testclient import TestClient

from cato_deal_intel import api
from cato_deal_intel.data import SourceData
from cato_deal_intel.llm import FakeLLM
from cato_deal_intel.retrieval import EvidenceRetriever


def test_health_endpoint() -> None:
    response = TestClient(api.app).get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_brief_endpoint_reuses_workflow(monkeypatch, tmp_path) -> None:
    qdrant_path = tmp_path / "qdrant"
    EvidenceRetriever(path=qdrant_path).index(SourceData(api.DATA_ROOT).evidence())
    monkeypatch.setattr(api, "ARTIFACT_ROOT", tmp_path)
    monkeypatch.setattr(api, "configured_llm", lambda: FakeLLM())
    monkeypatch.setattr(api, "configured_embedding_provider", lambda: None)
    monkeypatch.setattr(api, "DEFAULT_QDRANT_PATH", qdrant_path)

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
