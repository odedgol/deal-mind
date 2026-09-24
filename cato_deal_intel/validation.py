from collections.abc import Sequence

from .models import AgentOutput, EvidenceItem, Finding, RecommendedAction, StrategyOutput


def validate_citations(
    outputs: list[AgentOutput | StrategyOutput],
    evidence: list[EvidenceItem],
) -> None:
    valid_ids = {item.evidence_id for item in evidence}
    cited_ids = {
        evidence_id
        for output in outputs
        for item in _items_with_evidence(output)
        for evidence_id in item.evidence_ids
    }
    invalid_ids = cited_ids - valid_ids
    if invalid_ids:
        raise ValueError(f"Agent cited evidence outside authorized context: {sorted(invalid_ids)}")


def _items_with_evidence(
    output: AgentOutput | StrategyOutput,
) -> Sequence[Finding | RecommendedAction]:
    if isinstance(output, AgentOutput):
        return output.findings
    return output.actions
