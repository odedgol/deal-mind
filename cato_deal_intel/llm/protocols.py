from dataclasses import dataclass
from typing import Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMProvider(Protocol):
    def complete(self, *, system: str, user: str, output_type: type[T]) -> T: ...


@dataclass(frozen=True)
class RetryConfig:
    max_retries: int = 2
    timeout_seconds: float = 30.0
    backoff_seconds: float = 0.5


@dataclass(frozen=True)
class UsageSnapshot:
    model: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float
