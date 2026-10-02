"""Exercise fresh-process startup without a developer's existing Qdrant index."""

import os
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

ROOT = Path(__file__).parents[1]


def _run_python(tmp_path: Path, code: str, *args: str) -> str:
    source_data = tmp_path / "synthetic_data"
    if not source_data.exists():
        source_data.symlink_to(ROOT / "synthetic_data", target_is_directory=True)
    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT),
        "CATO_FAKE_LLM": "1",
        "OPENAI_API_KEY": "",
        "CATO_QDRANT_PATH": str(tmp_path / "qdrant"),
        "CATO_LLM_BUDGET_LEDGER_PATH": str(tmp_path / "budget.json"),
    }
    result = subprocess.run(
        [sys.executable, "-c", dedent(code), *args],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    return result.stdout


def test_api_and_cli_import_health_and_denial_need_no_index(tmp_path: Path) -> None:
    _run_python(
        tmp_path,
        """
        from fastapi.testclient import TestClient
        from cato_deal_intel.api.app import app
        from cato_deal_intel.cli import app as cli

        client = TestClient(app)
        assert client.get("/health").json() == {"status": "ok"}
        denied = client.post(
            "/brief", json={"opportunity_id": "OPP-1003", "user_id": "USR-5007"}
        )
        assert denied.status_code == 200
        assert denied.json()["status"] == "denied"
        """,
    )
    assert not (tmp_path / "qdrant").exists()


def test_cli_can_ingest_then_search_a_fresh_index(tmp_path: Path) -> None:
    entrypoint = "from cato_deal_intel.cli import app; app()"
    ingested = _run_python(tmp_path, entrypoint, "ingest")
    assert "Indexed" in ingested
    assert (tmp_path / "qdrant" / "meta.json").exists()

    results = _run_python(
        tmp_path,
        entrypoint,
        "search",
        "--opportunity", "OPP-1001",
        "--user", "USR-5001",
        "--query", "buyer objections",
    )
    assert results.strip()


def test_missing_index_error_stays_actionable_across_requests(tmp_path: Path) -> None:
    _run_python(
        tmp_path,
        """
        from fastapi.testclient import TestClient
        from cato_deal_intel.api.app import app
        from cato_deal_intel.api import dependencies as deps

        client = TestClient(app)
        try:
            for _ in range(2):
                try:
                    client.post(
                        "/brief",
                        json={"opportunity_id": "OPP-1001", "user_id": "USR-5001"},
                    )
                except RuntimeError as error:
                    assert "Qdrant index not found" in str(error), str(error)
                else:
                    raise AssertionError("Authorized retrieval must require ingestion")
        finally:
            deps.QDRANT_CLIENTS.close()
        """,
    )
