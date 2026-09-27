"""Shared client factories for local and service-backed infrastructure."""

from dataclasses import dataclass, field
from pathlib import Path
from threading import Lock

from qdrant_client import QdrantClient


@dataclass
class QdrantClientFactory:
    """Own one Qdrant client for the lifetime of an application component."""

    path: Path
    _client: QdrantClient | None = field(default=None, init=False)
    _initialization_lock: Lock = field(default_factory=Lock, init=False, repr=False)

    def __call__(self) -> QdrantClient:
        """Return the shared client, creating it lazily on first use."""
        client = self._client
        if client is None:
            with self._initialization_lock:
                client = self._client
                if client is None:
                    client = QdrantClient(path=str(self.path))
                    self._client = client
        return client

    def close(self) -> None:
        """Release the owned client during application shutdown."""
        client = self._client
        if client is not None:
            client.close()
            self._client = None
