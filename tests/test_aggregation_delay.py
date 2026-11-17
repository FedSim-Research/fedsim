import numpy as np
import pytest

from fedsim.engines.spyker.server import SpykerServer
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


@pytest.fixture
def make_server(local_actor, monkeypatch):
    def make(**spyker):
        config = FullConfiguration()
        for key, value in spyker.items():
            setattr(config.spyker, key, value)
        specs = {"A": ServerSpec("A", "A", Performance(10, 0), {}, 1000, 1000)}
        context = SimulationContext("orchestrator", {}, specs)
        server = local_actor(SpykerServer, "A", config, context)
        server.set_orchestrator("orchestrator")
        server.set_initial_weights([np.array([10.0])])
        server.self_ref = "self"
        server.assigned_client_instances = {"c": "client"}
        monkeypatch.setattr("fedsim.engines.spyker.server.ray.put", lambda value: value)
        server.scheduled = []
        server.streams_used = []
        monkeypatch.setattr(
            server, "_schedule_event", lambda **kwargs: server.scheduled.append(kwargs)
        )
        original = server.random_streams.stream
        monkeypatch.setattr(
            server.random_streams,
            "stream",
            lambda *key: server.streams_used.append(key) or original(*key),
        )
        return server

    return make


def send_update(server):
    server.on_client_update({"client_id": "c", "metrics": {"ref_model_age": 0}}, [np.array([12.0])])
    return [event for event in server.scheduled if event["event_type"] == "START_FIT"]


def test_default_dispatch_has_no_delay_and_draws_no_aggregation_stream(make_server):
    server = make_server()
    (event,) = send_update(server)
    assert event["delay"] == 0.0
    assert ("aggregation",) not in server.streams_used


def test_enabled_adds_aggregation_time_to_dispatch(make_server):
    server = make_server(aggregation_delay=True)
    expected = server._get_model_size_bytes() / 10
    (event,) = send_update(server)
    assert event["delay"] == pytest.approx(expected)
    assert expected > 0
    assert ("aggregation",) in server.streams_used


def test_response_delay_does_not_claim_delayed_model_visibility(make_server):
    server = make_server(aggregation_delay=True)
    (event,) = send_update(server)
    assert server.current_virtual_time == 0
    assert server.get_global_model()[0][0] == pytest.approx(11.2)
    assert event["delay"] > 0
