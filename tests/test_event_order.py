from types import SimpleNamespace

import pytest

from fedsim.simulation import orchestrator


@pytest.mark.parametrize("reverse_completion", [False, True])
@pytest.mark.parametrize("event_order", ["completion", "parent"])
def test_parent_frontier_order_is_independent_of_future_completion(
    monkeypatch, event_order, reverse_completion
):
    monkeypatch.setenv("FEDSIM_EVENT_LOG", "off")
    completed, dispatched, outputs = {}, [], []

    def dispatch(payload, **kwargs):
        key = payload["key"]
        dispatched.append(key)
        future = "future-" + key
        if key.startswith("parent"):
            suffix = key[-1]
            completed[future] = [(0, actor, "handle_event", {"key": "child" + suffix})]
        else:
            outputs.append(key)
            completed[future] = []
        return future

    actor = SimpleNamespace(handle_event=SimpleNamespace(remote=dispatch))

    def wait(refs, **kwargs):
        selected = refs[-1] if reverse_completion else refs[0]
        return [selected], [ref for ref in refs if ref != selected]

    monkeypatch.setattr(orchestrator.ray, "wait", wait)
    monkeypatch.setattr(orchestrator.ray, "get", completed.__getitem__)
    kernel = orchestrator.SimulationOrchestrator.__ray_metadata__.modified_class(
        event_order=event_order
    )
    for suffix in ("A", "B"):
        kernel.add_event(0, actor, "handle_event", {"key": "parent" + suffix})
    kernel.run_until(0)
    expected = ["childA", "childB"]
    if event_order == "completion" and reverse_completion:
        expected.reverse()
    assert outputs == expected
    if event_order == "parent":
        assert dispatched == ["parentA", "parentB", "childA", "childB"]


def test_ordering_mode_must_be_explicitly_supported(monkeypatch):
    monkeypatch.setenv("FEDSIM_EVENT_LOG", "off")
    with pytest.raises(ValueError, match="event_order"):
        orchestrator.SimulationOrchestrator.__ray_metadata__.modified_class(event_order="fastest")


def test_metadata_digest_does_not_restrict_custom_event_payloads(monkeypatch):
    from unittest.mock import Mock

    monkeypatch.setenv("FEDSIM_EVENT_LOG", "off")
    callback = Mock(return_value="future")
    actor = SimpleNamespace(handle_event=SimpleNamespace(remote=callback))
    monkeypatch.setattr(orchestrator.ray, "wait", lambda refs, **kwargs: (refs, []))
    monkeypatch.setattr(orchestrator.ray, "get", lambda ref: [])
    kernel = orchestrator.SimulationOrchestrator.__ray_metadata__.modified_class()
    payload = {"event_type": "CUSTOM", "data": None}
    kernel.add_event(0, actor, "handle_event", payload)
    kernel.run_until(0)
    callback.assert_called_once_with(payload)
    assert kernel.get_execution_summary()["dispatch_counts"] == {"CUSTOM": 1}
