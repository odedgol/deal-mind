"""Persists and updates local demo approval requests alongside their runs."""

import json
import os
import tempfile
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from ..models import AgentTrace, ApprovalRecord, ApprovalRequest, Brief


class ApprovalStore:
    def __init__(self, artifacts_root: Path) -> None:
        self.artifacts_root = artifacts_root

    def create(self, request: ApprovalRequest) -> None:
        self._write(self._request_path(request.run_id), request)

    def find(self, run_id: str) -> ApprovalRequest | None:
        path = self._request_path(run_id)
        if not path.exists():
            return None
        return ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))

    def inbox(self, user_id: str) -> list[tuple[ApprovalRequest, Brief]]:
        results = []
        for path in self.artifacts_root.glob("*/approval_request.json"):
            request = ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))
            if request.status != "pending" or user_id not in request.eligible_approver_user_ids:
                continue
            brief_path = path.parent / "brief.json"
            if brief_path.exists():
                brief = Brief.model_validate_json(brief_path.read_text(encoding="utf-8"))
                results.append((request, brief))
        return results

    def requester_runs(self, user_id: str) -> list[Brief]:
        """Return approval-routed briefs owned by this requester, without reviewer details."""
        briefs = []
        for path in self.artifacts_root.glob("*/approval_request.json"):
            request = ApprovalRequest.model_validate_json(path.read_text(encoding="utf-8"))
            if request.requester_user_id != user_id:
                continue
            brief_path = path.parent / "brief.json"
            if brief_path.exists():
                briefs.append(Brief.model_validate_json(brief_path.read_text(encoding="utf-8")))
        return briefs

    def decide(
        self,
        run_id: str,
        *,
        reviewer_user_id: str,
        decision: Literal["approved", "rejected"],
        comment: str | None,
    ) -> tuple[ApprovalRequest, Brief]:
        request = self.find(run_id)
        if request is None:
            raise FileNotFoundError(run_id)
        if request.status != "pending":
            raise ValueError("This approval request has already been decided.")
        if reviewer_user_id not in request.eligible_approver_user_ids:
            raise PermissionError("This user is not eligible to decide this request.")

        decided_at = datetime.now(UTC)
        updated_request = request.model_copy(
            update={
                "status": decision,
                "reviewer_user_id": reviewer_user_id,
                "comment": comment,
                "decided_at": decided_at,
            }
        )
        run_dir = self.artifacts_root / run_id
        brief_path = run_dir / "brief.json"
        brief = Brief.model_validate_json(brief_path.read_text(encoding="utf-8"))
        updated_brief = brief.model_copy(
            update={
                "run_status": "completed" if decision == "approved" else "rejected",
                "confidence_and_review_warnings": [
                    warning
                    for warning in brief.confidence_and_review_warnings
                    if not warning.startswith("Approval required:")
                ],
            }
        )

        approvals_path = run_dir / "approval.json"
        approvals = [
            ApprovalRecord.model_validate(item)
            for item in json.loads(approvals_path.read_text(encoding="utf-8"))
        ]
        decided_approvals = [
            approval.model_copy(
                update={"decision": decision, "comment": comment, "timestamp": decided_at}
            )
            for approval in approvals
        ]
        self._write(self._request_path(run_id), updated_request)
        self._write(brief_path, updated_brief)
        self._write(approvals_path, decided_approvals)
        self._write(run_dir / "brief.md", _brief_markdown(updated_brief))
        self._append_decision_trace(run_dir, run_id, reviewer_user_id, decision, decided_at)
        return updated_request, updated_brief

    def _append_decision_trace(
        self, run_dir: Path, run_id: str, reviewer: str, decision: str, decided_at: datetime
    ) -> None:
        path = run_dir / "trace.json"
        traces = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
        traces.append(
            AgentTrace(
                trace_id=uuid.uuid4().hex,
                run_id=run_id,
                event_type="approval",
                name="Deal Desk approval decision",
                prompt_version="local-demo-v1",
                status="completed",
                started_at=decided_at,
                completed_at=decided_at,
                metadata={"decision": decision, "reviewer_user_id": reviewer},
            ).model_dump(mode="json")
        )
        self._write(path, traces)

    def _request_path(self, run_id: str) -> Path:
        return self.artifacts_root / run_id / "approval_request.json"

    @staticmethod
    def _write(path: Path, value: object) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        serialized = _to_json(value)
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, delete=False
        ) as handle:
            temporary_path = Path(handle.name)
            content = (
                serialized if isinstance(serialized, str) else json.dumps(serialized, indent=2)
            )
            handle.write(content + "\n")
        os.replace(temporary_path, path)


def _brief_markdown(brief: Brief) -> str:
    """Keep the human-readable artifact in sync with the reviewed run status."""
    from .artifact_store import _to_markdown

    return _to_markdown(brief)


def _to_json(value: object) -> object:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")
    if isinstance(value, list):
        return [_to_json(item) for item in value]
    if isinstance(value, dict):
        return {key: _to_json(item) for key, item in value.items()}
    return value
