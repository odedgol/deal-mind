import json
import os
from collections.abc import Iterable
from typing import Any, Protocol, TypeVar

from openai import OpenAI
from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


class LLMAdapter(Protocol):
    def complete(self, *, system: str, user: str, output_type: type[T]) -> T: ...


class FakeLLM:
    """Small deterministic adapter used by tests and offline development."""

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        del system
        payload = json.loads(user)
        evidence_ids = [item["evidence_id"] for item in payload.get("evidence", [])[:3]]
        if output_type.__name__ == "AgentOutput":
            result: dict[str, Any] = {
                "findings": [
                    {
                        "text": "The retrieved evidence shows an active negotiation dependency.",
                        "evidence_ids": evidence_ids,
                        "confidence": 0.82,
                    }
                ],
                "missing_information": [
                    "Confirm the final decision date with the buying committee."
                ],
            }
        else:
            result = {
                "summary": (
                    "The deal is actionable but requires owners for open buyer and "
                    "approval dependencies."
                ),
                "actions": [
                    {
                        "action": "Confirm open dependencies and document the negotiation path.",
                        "owner": "Account owner",
                        "rationale": "Open dependencies are the main remaining execution risk.",
                        "evidence_ids": evidence_ids,
                        "requires_approval": False,
                    }
                ],
                "warnings": ["Validate all customer-facing language before sharing externally."],
            }
        return output_type.model_validate(result)


class OpenAIAdapter:
    def __init__(self, model: str | None = None) -> None:
        self.client = OpenAI()
        configured_model = os.getenv("CATO_LLM_MODEL")
        self.model: str = model or configured_model or "gpt-4o-mini"

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=output_type,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("LLM returned no structured output")
        return parsed


def configured_llm() -> LLMAdapter:
    if os.getenv("CATO_FAKE_LLM") == "1":
        return FakeLLM()
    if not os.getenv("OPENAI_API_KEY"):
        raise RuntimeError("Set OPENAI_API_KEY or CATO_FAKE_LLM=1 for deterministic tests.")
    return OpenAIAdapter()


def evidence_payload(evidence: Iterable[Any]) -> list[dict[str, Any]]:
    return [item.model_dump(mode="json") for item in evidence]
