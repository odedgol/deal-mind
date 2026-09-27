import os
from collections.abc import Sequence
from hashlib import sha256

from openai import OpenAI

from ..llm.protocols import RetryConfig
from ..llm.retry import retry_call
from ..llm.settings import configured_retry_config


class EmbeddingProvider:
    dimensions: int

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        raise NotImplementedError


class OpenAIEmbeddingProvider(EmbeddingProvider):
    dimensions = 1536

    def __init__(self, model: str | None = None, retry_config: RetryConfig | None = None) -> None:
        self.model: str = model or os.getenv("CATO_EMBEDDING_MODEL") or "text-embedding-3-small"
        self.retry_config = retry_config or configured_retry_config()
        self.client = OpenAI(
            timeout=self.retry_config.timeout_seconds,
            max_retries=0,
        )

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        response = retry_call(
            lambda: self.client.embeddings.create(input=list(texts), model=self.model),
            config=self.retry_config,
        )
        return [list(item.embedding) for item in response.data]


class HashEmbeddingProvider(EmbeddingProvider):
    """Deterministic local embeddings for tests and offline development."""

    dimensions = 64

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._embed_one(text) for text in texts]

    def _embed_one(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in text.lower().split():
            digest = sha256(token.encode()).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            vector[index] += 1.0
        return vector


def configured_embedding_provider() -> EmbeddingProvider:
    if os.getenv("CATO_FAKE_LLM") == "1":
        return HashEmbeddingProvider()
    return OpenAIEmbeddingProvider()
