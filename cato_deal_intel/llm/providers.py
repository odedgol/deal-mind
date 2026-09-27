import logging
import os
from typing import TypeVar

from openai import OpenAI
from pydantic import BaseModel

from .protocols import RetryConfig
from .retry import retry_call
from .settings import configured_cost_controller, configured_retry_config

T = TypeVar("T", bound=BaseModel)
LOGGER = logging.getLogger("cato_deal_intel")


class OpenAIProvider:
    def __init__(self, model: str | None = None, retry_config: RetryConfig | None = None) -> None:
        self.retry_config = retry_config or configured_retry_config()
        self.client = OpenAI(
            timeout=self.retry_config.timeout_seconds,
            max_retries=0,
        )
        configured_model = os.getenv("CATO_LLM_MODEL")
        self.model: str = model or configured_model or "gpt-4o-mini"
        self.specialist_model = os.getenv("CATO_LLM_SPECIALIST_MODEL", self.model)
        self.strategy_model = os.getenv("CATO_LLM_STRATEGY_MODEL", self.model)
        self.cost_controller = configured_cost_controller()

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        return retry_call(
            lambda: self._complete_once(system, user, output_type),
            config=self.retry_config,
        )

    def _complete_once(self, system: str, user: str, output_type: type[T]) -> T:
        self.cost_controller.can_call()
        model = self._model_for(output_type)
        response = self.client.beta.chat.completions.parse(
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=output_type,
            temperature=0,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM returned no structured output")
        usage = response.usage
        if usage is not None:
            snapshot = self.cost_controller.record(
                model=model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
            )
            LOGGER.info(
                "llm.usage model=%s prompt_tokens=%s completion_tokens=%s "
                "cost_usd=%.6f total_cost_usd=%.6f",
                snapshot.model,
                snapshot.prompt_tokens,
                snapshot.completion_tokens,
                snapshot.cost_usd,
                self.cost_controller.total_cost_usd,
            )
        return parsed

    def _model_for(self, output_type: type[T]) -> str:
        return (
            self.strategy_model
            if output_type.__name__ == "StrategyOutput"
            else self.specialist_model
        )
