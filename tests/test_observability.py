import logging

from pytest import LogCaptureFixture, MonkeyPatch

from cato_deal_intel.observability import observed


def test_observability_can_be_disabled(
    monkeypatch: MonkeyPatch, caplog: LogCaptureFixture
) -> None:
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

    @observed(agent_name="test-agent", prompt_version="v1")
    def work() -> str:
        return "ok"

    assert work() == "ok"
    assert '"event": "agent.started"' in caplog.text
    assert '"event": "agent.completed"' in caplog.text
    assert "ok" not in caplog.text
