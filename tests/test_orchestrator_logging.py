import pytest

from fedsim.simulation import orchestrator


@pytest.mark.parametrize("value", [None, "", "on", "ON", " on ", "anything"])
def test_event_log_enabled_by_default_and_for_non_off_values(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("FEDSIM_EVENT_LOG", raising=False)
    else:
        monkeypatch.setenv("FEDSIM_EVENT_LOG", value)
    assert orchestrator._event_log_enabled() is True


@pytest.mark.parametrize("value", ["off", "OFF", " off "])
def test_event_log_disabled_by_off(monkeypatch, value):
    monkeypatch.setenv("FEDSIM_EVENT_LOG", value)
    assert orchestrator._event_log_enabled() is False
