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
        config.spyker.aggregation_bytes_per_second = 10
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


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
@pytest.mark.parametrize("rate", [None, True, 0, -1, float("nan"), float("inf")])
def test_enabled_delay_rejects_missing_or_invalid_rate_before_execution(architecture, rate):
    from test_builders import topology

    from fedsim.services.hierfl_simulation_builder import build_hierfl_simulation
    from fedsim.services.simulation_validation import validate_start_payload
    from fedsim.services.spyker_simulation_builder import build_spyker_simulation

    graph = topology(architecture)
    training = {"epochs": 1, "lr": 0.01}
    controls = {"aggregation_delay": True, "aggregation_bytes_per_second": rate}
    settings, spyker = (controls, {}) if architecture == "hierfl" else ({}, controls)
    with pytest.raises(ValueError, match="aggregation"):
        validate_start_payload(architecture, graph, training, settings, spyker)
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    kwargs = controls if architecture == "hierfl" else {"spyker_config": controls}
    with pytest.raises(ValueError, match="aggregation"):
        builder(graph, training_config=training, **kwargs)


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_api_throughput_reaches_built_engine(architecture, monkeypatch):
    from test_builders import topology

    from fedsim.api.routes.simulation import SimulationSettings, SpykerAlgorithmConfig
    from fedsim.services.controller import SimulationController
    from fedsim.services.simulation_validation import validate_start_payload

    graph = topology(architecture)
    model = SimulationSettings if architecture == "hierfl" else SpykerAlgorithmConfig
    controls = model(aggregation_delay=True, aggregation_bytes_per_second=100_000_000).model_dump(
        exclude_none=True
    )
    settings, spyker = (controls, {}) if architecture == "hierfl" else ({}, controls)
    training = {"epochs": 1, "lr": 0.01}
    validate_start_payload(architecture, graph, training, settings, spyker)
    controller = SimulationController(
        architecture,
        graph=graph,
        training_config=training,
        simulation_settings=settings,
        spyker_config=spyker,
    )
    monkeypatch.setattr("fedsim.learning.preload_dataset", lambda dataset_id: None)
    monkeypatch.setattr(controller, "_run_simulation", lambda *, builder, evaluator: builder())
    simulation = controller.start.__wrapped__(controller)
    config = simulation if architecture == "hierfl" else simulation.config.spyker
    assert config.aggregation_delay is True
    assert config.aggregation_bytes_per_second == 100_000_000


def test_coordinator_delay_counts_input_bytes_and_preserves_state_visibility(
    local_actor, monkeypatch
):
    from fedsim.engines.hierarchical import coordinator

    specs = {
        key: ServerSpec(key, key, Performance(2, 0), {}, 1000, 1000)
        for key in ("coordinator", "edge")
    }
    context = SimulationContext("orchestrator", {}, specs)
    server = local_actor(
        coordinator.SuperServer,
        "coordinator",
        [np.array([10.0])],
        1,
        {},
        context,
        aggregation_delay=True,
        aggregation_bytes_per_second=100,
    )
    server.edge_server_refs = {"edge": "edge-actor"}
    server.scheduled = []
    monkeypatch.setattr(server, "_schedule_event", lambda **event: server.scheduled.append(event))
    monkeypatch.setattr(coordinator, "estimate_transmission_time", lambda **kwargs: 0.125)
    server.on_server_message(
        {"type": "AGGREGATION_SYNC", "edge_server_id": "edge", "num_samples": 1}, [np.array([12.0])]
    )
    assert server.global_model_weights[0][0] == 12.0
    assert len(server.scheduled) == 1
    assert server.scheduled[0]["delay"] == pytest.approx(0.125 + 8 / 100)
