import os
import pickle
import random
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import torch
from torch import nn

from fedsim.clients import actor as client_actor
from fedsim.clients.training import TrainingClient
from fedsim.engines.hierarchical.coordinator import SuperServer
from fedsim.engines.hierarchical.edge import EdgeServer
from fedsim.engines.spyker.server import SpykerServer
from fedsim.learning import Net
from fedsim.services.controller import SimulationController
from fedsim.simulation.compute_model import estimate_training_time
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.randomness import RandomStreams, derive_seed
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


@pytest.fixture
def global_states():
    states = random.getstate(), np.random.get_state(), torch.get_rng_state().clone()
    yield states
    random.setstate(states[0])
    np.random.set_state(states[1])
    torch.set_rng_state(states[2])


def assert_global_states(states):
    assert random.getstate() == states[0]
    current = np.random.get_state()
    assert current[0] == states[1][0]
    np.testing.assert_array_equal(current[1], states[1][1])
    assert current[2:] == states[1][2:]
    assert torch.equal(torch.get_rng_state(), states[2])


def test_seeded_model_matches_previous_pytorch_initialization(global_states):
    # Construct the old layers in their original order with PyTorch's defaults.
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(42)
        layers = [
            nn.Conv2d(3, 32, 3, padding=1),
            nn.Conv2d(32, 64, 3, padding=1),
            nn.Conv2d(64, 128, 3, padding=1),
            nn.Linear(128 * 4 * 4, 256),
            nn.Linear(256, 10),
        ]
    model = Net(seed=42)
    for previous, current in zip(
        layers, (model.conv1, model.conv2, model.conv3, model.fc1, model.fc2)
    ):
        assert torch.equal(previous.weight, current.weight)
        assert torch.equal(previous.bias, current.bias)
    assert_global_states(global_states)


def test_parallel_model_initialization_is_isolated_and_repeatable(global_states):
    seeds = (42, 17, 42, 17)
    barrier = Barrier(len(seeds))

    def initialize(seed):
        barrier.wait(timeout=10)
        return Net(seed=seed).state_dict()

    with ThreadPoolExecutor(max_workers=len(seeds)) as threads:
        models = list(threads.map(initialize, seeds))
    for key in models[0]:
        assert torch.equal(models[0][key], models[2][key])
        assert torch.equal(models[1][key], models[3][key])
    assert not torch.equal(models[0]["fc2.weight"], models[1]["fc2.weight"])
    assert_global_states(global_states)


@pytest.mark.parametrize("extra_state", ["parameter", "layer", "buffer"])
def test_model_rejects_uncovered_state_before_allocating_memory(
    monkeypatch, global_states, extra_state
):
    linear = nn.Linear

    def extended_linear(*args, **kwargs):
        layer = linear(*args, **kwargs)
        if extra_state == "parameter":
            layer.register_parameter("extra", nn.Parameter(torch.empty(1, device="meta")))
        elif extra_state == "layer":
            layer.add_module("extra", linear(1, 1, device="meta"))
        else:
            layer.register_buffer("running_stat", torch.zeros(1, device="meta"))
        return layer

    allocation = Mock(side_effect=AssertionError("Uncovered state must fail before allocation"))
    monkeypatch.setattr(nn, "Linear", extended_linear)
    monkeypatch.setattr(Net, "to_empty", allocation)
    with pytest.raises(RuntimeError, match="complete_parameter_and_buffer_coverage"):
        Net(seed=42)
    allocation.assert_not_called()
    assert_global_states(global_states)


def test_unseeded_models_use_private_nondeterministic_generators(global_states):
    first, second = Net(), Net()
    assert not torch.equal(first.fc2.weight, second.fc2.weight)
    assert_global_states(global_states)


def test_training_client_initialization_does_not_reseed_other_components(
    monkeypatch, global_states
):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    first = TrainingClient(0, 2, seed=17)
    second = TrainingClient(1, 2, seed=17)
    for left, right in zip(first.get_parameters(), second.get_parameters()):
        np.testing.assert_array_equal(left, right)
    assert_global_states(global_states)


def test_controllers_do_not_change_global_random_states(global_states):
    barrier = Barrier(2)

    def run(seed):
        class Simulation:
            def build(self):
                barrier.wait(timeout=10)
                self.model = Net(seed=seed)

            def run(self):
                pass

        return SimulationController("test", simulation_settings={"seed": seed})._run_simulation(
            builder=Simulation, evaluator=Mock()
        )

    with ThreadPoolExecutor(max_workers=2) as threads:
        assert [result["seed"] for result in threads.map(run, (17, 42))] == [17, 42]
    assert_global_states(global_states)


def test_derived_seeds_are_stable_across_python_processes():
    code = (
        "from fedsim.simulation.randomness import derive_seed; "
        "print(derive_seed(42, 'server', 'edge', 'network', 'peer'))"
    )
    outputs = [
        subprocess.check_output(
            [sys.executable, "-c", code], env={**os.environ, "PYTHONHASHSEED": seed}, text=True
        ).strip()
        for seed in ("1", "9876")
    ]
    assert outputs[0] == outputs[1] == str(derive_seed(42, "server", "edge", "network", "peer"))
    assert outputs[0] == "9064406149002565742"
    assert derive_seed(42, "ab", "c") != derive_seed(42, "a", "bc")
    assert derive_seed(17, "a") != derive_seed(42, "a")


def test_named_streams_advance_independently_and_survive_serialization(global_states):
    streams = RandomStreams(42, "server", "edge")
    expected = RandomStreams(42, "server", "edge").stream("network", "peer")
    assert streams.stream("network", "peer").gauss(20, 3) == expected.gauss(20, 3)
    for _ in range(10):
        streams.stream("network", "unrelated").gauss(20, 3)
        streams.stream("training").gauss(0, 1)
    restored = pickle.loads(pickle.dumps(streams))
    next_value = expected.gauss(20, 3)
    assert streams.stream("network", "peer").gauss(20, 3) == next_value
    assert restored.stream("network", "peer").gauss(20, 3) == next_value
    assert_global_states(global_states)


def test_unseeded_streams_do_not_consume_global_random_state(global_states):
    streams = RandomStreams(None, "client")
    streams.stream("training").gauss(0, 1)
    streams.stream("network").gauss(0, 1)
    assert_global_states(global_states)


def test_compute_noise_uses_the_supplied_generator_and_zero_sigma_does_not_advance_it():
    rng = RandomStreams(42, "client").stream("training")
    spec = ClientSpec("client", "Client", Performance(10, 0), 10, 10)
    before = rng.getstate()
    assert estimate_training_time(spec, 20, 1, 1, rng=rng) == 2
    assert rng.getstate() == before
    spec.performance_metrics.performance_stddev = 0.2
    expected = random.Random()
    expected.setstate(before)
    assert estimate_training_time(spec, 20, 1, 1, rng=rng) == 2 + expected.gauss(0, 0.2)


def test_client_timing_is_seeded_without_global_draws(monkeypatch, local_actor, global_states):
    link = Network(20, 3, 0.05, 0.01)
    spec = ClientSpec("client", "Client", Performance(10, 0.2), 20, 20)
    server = ServerSpec("server", "Server", Performance(100, 0), {"client": link}, 100, 40)
    context = SimulationContext(None, {"client": spec}, {"server": server}, seed=42)
    weights = [np.zeros(100, dtype=np.float32)]
    monkeypatch.setattr(
        client_actor,
        "TrainingClient",
        lambda **kwargs: SimpleNamespace(
            fit=lambda **kwargs: {"parameters": weights, "num_examples": 10, "metrics": {}}
        ),
    )

    def timings(seed):
        actor = local_actor(
            client_actor.VirtualClientActor,
            "client",
            {"dataset_partition_id": 0, "total_partitions": 1, "seed": seed},
            context,
        )
        return [
            actor.handle_event(
                {
                    "event_type": "START_FIT",
                    "trigger_time": 0,
                    "data": {"server_id": "server", "server_ref": "server", "config": {}},
                },
                direct_refs=weights,
            )[0][0]
            for _ in range(3)
        ]

    first = timings(42)
    assert first == timings(42)
    assert first != timings(17)
    assert len(set(first)) > 1
    assert_global_states(global_states)


@pytest.mark.parametrize("kind", ["coordinator", "edge", "spyker"])
def test_server_network_timing_uses_run_seed(local_actor, kind, global_states):
    link = Network(20, 3, 0.05, 0.01)
    specs = {
        name: ServerSpec(name, name, Performance(10, 0), {peer: link}, 100, 100)
        for name, peer in (("A", "B"), ("B", "A"))
    }
    weights = [np.zeros(100, dtype=np.float32)]

    def timings(seed):
        context = SimulationContext("orchestrator", {}, specs, seed=seed)
        context.set_server_actor_handles({"A": "A", "B": "B"})
        if kind == "coordinator":
            actor = local_actor(SuperServer, "A", weights, 1, {}, context)
            actor.set_edge_servers({"B": "B"})
        elif kind == "edge":
            actor = local_actor(EdgeServer, "A", "B", "B", 1, context)
            actor.global_model_weights = weights
        else:
            actor = local_actor(SpykerServer, "A", FullConfiguration(), context)
        actor.set_orchestrator("orchestrator")
        delays = []
        for _ in range(3):
            if kind == "coordinator":
                actor._broadcast_global_model()
            elif kind == "edge":
                actor.client_updates_buffer["client"] = (weights, 10)
                actor._aggregate_and_send_upstream()
            else:
                actor._send_server_message("B", "TOKEN", {})
            delays.append(actor._get_and_clear_events()[0][0])
        return delays

    first = timings(42)
    assert first == timings(42)
    assert first != timings(17)
    assert len(set(first)) > 1
    assert_global_states(global_states)
