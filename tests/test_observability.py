import logging

from pytest import LogCaptureFixture, MonkeyPatch

from cato_deal_intel.observability.tracing import observed


def test_observability_can_be_disabled(monkeypatch: MonkeyPatch, caplog: LogCaptureFixture) -> None:
    monkeypatch.setenv("CATO_OBSERVABILITY", "false")

    @observed(agent_name="test-agent", prompt_version="v1")
    def work() -> str:
        return "ok"

    with caplog.at_level(logging.INFO):
        assert work() == "ok"

    assert "test-agent" not in caplog.text


def test_observability_logs_safe_agent_lifecycle(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    monkeypatch.setenv("CATO_OBSERVABILITY", "true")
    monkeypatch.setenv("CATO_OBSERVABILITY_IO", "metadata")

    @observed(agent_name="test-agent", prompt_version="v1")
    def work() -> str:
        return "ok"

    assert work() == "ok"
    assert '"event": "agent.started"' in caplog.text
    assert '"event": "agent.completed"' in caplog.text
    assert "ok" not in caplog.text


def test_observability_logs_io_metadata_without_payload(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    monkeypatch.setenv("CATO_OBSERVABILITY", "true")
    monkeypatch.setenv("CATO_OBSERVABILITY_IO", "metadata")

    @observed(agent_name="test-agent", prompt_version="v1")
    def work(value: str) -> str:
        return value

    work("private input")

    assert '"input_types": ["str"]' in caplog.text
    assert "private input" not in caplog.text


def test_full_io_logging_truncates_long_values(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
    monkeypatch.setenv("CATO_OBSERVABILITY", "true")
    monkeypatch.setenv("CATO_OBSERVABILITY_IO", "full")

    @observed(agent_name="test-agent", prompt_version="v1")
    def work(value: str) -> str:
        return value

    work("x" * 501)

    assert "...[truncated]" in caplog.text
