from pathlib import Path

from cato_deal_intel.client_factory import QdrantClientFactory


def test_qdrant_client_factory_reuses_and_closes_client(tmp_path: Path) -> None:
    factory = QdrantClientFactory(tmp_path / "qdrant")

    first = factory()
    second = factory()

    assert first is second
    factory.close()
    assert factory._client is None
