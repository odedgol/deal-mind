from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from cato_deal_intel.storage.client_factory import QdrantClientFactory


def test_qdrant_client_factory_reuses_and_closes_client(tmp_path: Path) -> None:
    factory = QdrantClientFactory(tmp_path / "qdrant")

    first = factory()
    second = factory()

    assert first is second
    factory.close()
    assert factory._client is None


def test_qdrant_client_factory_initializes_once_under_concurrency(tmp_path: Path) -> None:
    factory = QdrantClientFactory(tmp_path / "qdrant")

    with ThreadPoolExecutor(max_workers=8) as executor:
        clients = list(executor.map(lambda _: factory(), range(8)))

    assert len({id(client) for client in clients}) == 1
    factory.close()
