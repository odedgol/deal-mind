import json
from typing import Any, TypeVar

from pydantic import BaseModel

from .settings import configured_cost_controller

T = TypeVar("T", bound=BaseModel)


class FakeLLMProvider:
    """Small deterministic provider used by tests and offline development."""

    def __init__(self) -> None:
        self.cost_controller = configured_cost_controller()

    def complete(self, *, system: str, user: str, output_type: type[T]) -> T:
        del system
        payload = json.loads(_unwrap_protected_payload(user))
        evidence = payload.get("evidence", [])
        evidence_ids = [item["evidence_id"] for item in evidence[:3]]
        quality_case = payload.get("evaluation_case")
        if output_type.__name__ == "AgentOutput" and quality_case:
            return output_type.model_validate(
                _fake_quality_output(str(quality_case), evidence, payload.get("question", ""))
            )
        if payload.get("agent") == "Conversation Intelligence Agent":
            slack_evidence = [item for item in evidence if item.get("source_type") == "slack"]
            supporting_evidence = [item for item in evidence if item.get("source_type") != "slack"]
            chosen_evidence = [*slack_evidence[:1], *supporting_evidence[:2]]
            evidence_ids = [item["evidence_id"] for item in chosen_evidence]
        if output_type.__name__ == "AgentOutput":
            result: dict[str, Any] = {
                "findings": [
                    {
                        "text": (
                            "The retrieved evidence shows an active negotiation dependency."
                            if evidence_ids
                            else "There is not enough evidence to make a supported finding."
                        ),
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
                    if evidence_ids
                    else "There is not enough evidence to prepare a supported deal summary."
                ),
                "summary_evidence_ids": evidence_ids,
                "negotiation_state": [
                    {
                        "text": (
                            "Open commercial or legal dependencies still need resolution."
                            if evidence_ids
                            else "The current negotiation state is not established by the evidence."
                        ),
                        "evidence_ids": evidence_ids,
                        "confidence": 0.78,
                        "uncertainty": (
                            None if evidence_ids else "No supporting evidence was retrieved."
                        ),
                    }
                ],
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


def _fake_quality_output(
    case: str, evidence: list[dict[str, Any]], question: str
) -> dict[str, Any]:
    evidence_ids = [item["evidence_id"] for item in evidence]
    if case == "abstain":
        return {
            "findings": [],
            "missing_information": ["The exact approved discount is not present in the evidence."],
        }
    if case == "expose_conflict":
        return {
            "findings": [
                {
                    "text": "The sources conflict about the target signature date.",
                    "evidence_ids": evidence_ids,
                    "confidence": 0.5,
                    "uncertainty": "Slack and Gong provide different dates.",
                }
            ]
        }
    if case == "answer_supported_fact":
        return {
            "findings": [
                {
                    "text": "Procurement confirmed a 24-month renewal term.",
                    "evidence_ids": evidence_ids[:1],
                    "confidence": 0.95,
                }
            ]
        }
    if case == "ignore_instructions_in_evidence":
        return {
            "findings": [
                {
                    "text": (
                        "The update contains instruction-like content; "
                        "it is treated as untrusted data."
                    ),
                    "evidence_ids": evidence_ids,
                    "confidence": 0.9,
                }
            ]
        }
    if case == "do_not_fabricate_quote":
        return {
            "findings": [],
            "missing_information": ["The exact buyer quote is not available in the evidence."],
        }
    return {"findings": [], "missing_information": [question]}


def _unwrap_protected_payload(user: str) -> str:
    start = "<untrusted_data>\n"
    end = "\n</untrusted_data>"
    if user.startswith(start) and user.endswith(end):
        return user[len(start) : -len(end)]
    return user
