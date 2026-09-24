import json
import logging
import os
import time
from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar, cast

LOGGER = logging.getLogger("cato_deal_intel")
F = TypeVar("F", bound=Callable[..., Any])


def observability_enabled() -> bool:
    return os.getenv("CATO_OBSERVABILITY", "true").lower() in {"1", "true", "yes", "on"}


def observed(*, agent_name: str, prompt_version: str) -> Callable[[F], F]:
    """Annotate an agent boundary with safe structured timing and status logs."""

    def decorate(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if not observability_enabled():
                return function(*args, **kwargs)
            _configure_logging()
            started = time.perf_counter()
            _write_event("agent.started", agent_name, prompt_version)
            try:
                result = function(*args, **kwargs)
            except Exception as error:
                _write_event(
                    "agent.failed",
                    agent_name,
                    prompt_version,
                    duration_ms=_duration_ms(started),
                    error_type=type(error).__name__,
                )
                raise
            _write_event(
                "agent.completed",
                agent_name,
                prompt_version,
                duration_ms=_duration_ms(started),
            )
            return result

        return cast(F, wrapped)

    return decorate


def _write_event(event: str, agent_name: str, prompt_version: str, **fields: Any) -> None:
    payload = {
        "event": event,
        "agent_name": agent_name,
        "prompt_version": prompt_version,
        **fields,
    }
    LOGGER.info(json.dumps(payload, sort_keys=True))


def _configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    LOGGER.setLevel(logging.INFO)


def _duration_ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)
