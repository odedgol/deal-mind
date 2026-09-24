"""Deterministic evaluation runner for the synthetic golden set."""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from qdrant_client import QdrantClient

from .client_factory import QdrantClientFactory
from .data import SourceData
from .llm import FakeLLM
from .models import Brief, DeniedResult
from .retrieval import EvidenceRetriever
from .workflow import create_brief

EvaluationStatus = Literal["brief", "denied"]


@dataclass(frozen=True)
class GoldenCase:
    name: str
    opportunity_id: str
    user_id: str
    expected_status: EvaluationStatus
    approval_required: bool
    required_source_types: list[str]


@dataclass(frozen=True)
class CaseResult:
    name: str
    passed: bool
    checks: dict[str, bool]


@dataclass(frozen=True)
class EvaluationReport:
    total_cases: int
    passed_cases: int
    results: list[CaseResult]

    @property
    def pass_rate(self) -> float:
        return self.passed_cases / self.total_cases if self.total_cases else 1.0


def load_golden_set(path: Path) -> list[GoldenCase]:
    cases = json.loads(path.read_text(encoding="utf-8"))
    return [GoldenCase(**case) for case in cases]


def run_golden_evaluation(
    *,
    root: Path,
    qdrant_path: Path,
    artifacts_root: Path,
    golden_path: Path,
) -> EvaluationReport:
    source = SourceData(root)
    clients = QdrantClientFactory(qdrant_path)
    client = clients()
    try:
        EvidenceRetriever(client=client).rebuild(source.evidence())
        results = [
            _evaluate_case(case, root, qdrant_path, artifacts_root, client)
            for case in load_golden_set(golden_path)
        ]
    finally:
        clients.close()
    return EvaluationReport(
        total_cases=len(results),
        passed_cases=sum(result.passed for result in results),
        results=results,
    )


def _evaluate_case(
    case: GoldenCase,
    root: Path,
    qdrant_path: Path,
    artifacts_root: Path,
    client: QdrantClient,
) -> CaseResult:
    result = create_brief(
        root=root,
        artifacts_root=artifacts_root,
        opportunity_id=case.opportunity_id,
        user_id=case.user_id,
        llm=FakeLLM(),
        approval_decision="pending",
        qdrant_path=qdrant_path,
        qdrant_client=client,
    )
    checks = {
        "status": _status_matches(result, case.expected_status),
        "approval": _approval_matches(result, case.approval_required),
        "sources": _sources_match(result, case.required_source_types),
        "citations": _citations_are_grounded(result),
    }
    return CaseResult(case.name, all(checks.values()), checks)


def _status_matches(result: Brief | DeniedResult, expected: EvaluationStatus) -> bool:
    return (expected == "brief" and isinstance(result, Brief)) or (
        expected == "denied" and isinstance(result, DeniedResult)
    )


def _approval_matches(result: Brief | DeniedResult, expected: bool) -> bool:
    if not isinstance(result, Brief):
        return not expected
    return any(action.requires_approval for action in result.recommended_next_actions) == expected


def _sources_match(result: Brief | DeniedResult, required: list[str]) -> bool:
    if not isinstance(result, Brief):
        return not required
    source_types = {item.source_type for item in result.source_evidence}
    return set(required).issubset(source_types)


def _citations_are_grounded(result: Brief | DeniedResult) -> bool:
    if not isinstance(result, Brief):
        return True
    evidence_ids = {item.evidence_id for item in result.source_evidence}
    cited_ids = {
        evidence_id
        for finding in [*result.buyer_goals, *result.stakeholder_map, *result.negotiation_state]
        for evidence_id in finding.evidence_ids
    }
    cited_ids.update(
        evidence_id
        for action in result.recommended_next_actions
        for evidence_id in action.evidence_ids
    )
    return cited_ids.issubset(evidence_ids)
