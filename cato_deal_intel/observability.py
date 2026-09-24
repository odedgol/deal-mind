import json
import logging
import os
import time
from collections.abc import Callable
from functools import wraps
from threading import Lock
from typing import Any, TypeVar, cast

from .models import AgentTrace

LOGGER = logging.getLogger("cato_deal_intel")
F = TypeVar("F", bound=Callable[..., Any])


class AgentTraceCollector:
    """Collect traces safely when parallel LangGraph nodes are running."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._traces: dict[tuple[str, str], AgentTrace] = {}

    def record(self, trace: AgentTrace) -> None:
        with self._lock:
            self._traces[(trace.run_id, trace.agent_name)] = trace

    @property
    def traces(self) -> list[AgentTrace]:
        with self._lock:
            return list(self._traces.values())


def observability_enabled() -> bool:
    return os.getenv("CATO_OBSERVABILITY", "true").lower() in {"1", "true", "yes", "on"}


def io_logging_mode() -> str:
    mode = os.getenv("CATO_OBSERVABILITY_IO", "metadata").lower()
    return mode if mode in {"metadata", "full"} else "metadata"


def observed(*, agent_name: str, prompt_version: str) -> Callable[[F], F]:
    """Annotate an agent boundary with safe structured timing and status logs."""

    def decorate(function: F) -> F:
        @wraps(function)
        def wrapped(*args: Any, **kwargs: Any) -> Any:
            if not observability_enabled():
                return function(*args, **kwargs)
            _configure_logging()
            started = time.perf_counter()
            _write_event(
                "agent.started",
                agent_name,
                prompt_version,
                **_io_fields(args, kwargs, None),
            )
            try:
                result = function(*args, **kwargs)
            except Exception as error:
                _write_event(
                    "agent.failed",
                    agent_name,
                    prompt_version,
                    duration_ms=_duration_ms(started),
                    error_type=type(error).__name__,
                    **_io_fields(args, kwargs, None),
                )
                raise
            _write_event(
                "agent.completed",
                agent_name,
                prompt_version,
                duration_ms=_duration_ms(started),
                **_io_fields(args, kwargs, result),
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


def _io_fields(args: tuple[Any, ...], kwargs: dict[str, Any], result: Any) -> dict[str, Any]:
    if io_logging_mode() == "full":
        return {
            "input": _safe_snapshot({"args": args, "kwargs": kwargs}),
            "output": _safe_snapshot(result),
        }
    return {
        "input_types": [type(value).__name__ for value in args],
        "input_keyword_names": sorted(kwargs),
        "input_evidence_count": _evidence_count(args, kwargs),
        "output_type": type(result).__name__ if result is not None else None,
        "output_item_count": _output_item_count(result),
        "output_citation_count": _output_citation_count(result),
    }


def _evidence_count(args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
    values = (*args, *kwargs.values())
    return sum(len(getattr(value, "evidence", [])) for value in values)


def _output_item_count(value: Any) -> int | None:
    for field in ("findings", "actions"):
        items = getattr(value, field, None)
        if items is not None:
            return len(items)
    return None


def _output_citation_count(value: Any) -> int | None:
    items = getattr(value, "findings", None) or getattr(value, "actions", None)
    if items is None:
        return None
    return sum(len(getattr(item, "evidence_ids", [])) for item in items)


def _safe_snapshot(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return _redact_value(value)
    if hasattr(value, "model_dump"):
        return _safe_snapshot(value.model_dump(mode="json"))
    if isinstance(value, dict):
        return {
            str(key): "<redacted>" if _is_sensitive_key(str(key)) else _safe_snapshot(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [_safe_snapshot(item) for item in value]
    return f"<{type(value).__name__}>"


def _redact_value(value: Any) -> Any:
    if isinstance(value, str) and len(value) > 500:
        return value[:500] + "...[truncated]"
    return value


def _is_sensitive_key(key: str) -> bool:
    sensitive_terms = {"api_key", "password", "phone", "email", "secret", "token"}
    normalized = key.lower()
    return any(term in normalized for term in sensitive_terms)
