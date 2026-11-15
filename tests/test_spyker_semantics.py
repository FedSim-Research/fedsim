"""Small reference cases for the specified asynchronous update rules."""

import math

import numpy as np
import pytest

from fedsim.engines.spyker.server import SpykerServer
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


@pytest.fixture
def make_server(local_actor):
    def create():
        link = Network(1, 0, 0, 0)
        specs = {
            name: ServerSpec(name, name, Performance(10, 0), {peer: link}, 1000, 1000)
            for name, peer in (("A", "B"), ("B", "A"))
        }
        context = SimulationContext("orchestrator", {}, specs)
        context.set_server_actor_handles({"A": "A", "B": "B"})
        server = local_actor(SpykerServer, "A", FullConfiguration(), context)
        server.set_topology({"B": link}, "B", [])
        server.set_orchestrator("orchestrator")
        server.set_initial_weights([np.array([10.0], dtype=np.float64)])
        server.model_age = 10
        server.server_ages = {"A": 10, "B": 10}
        server._schedule_client_task = lambda _client_id: None
        return server

    return create


def peer_update(server, age, value):
    server.on_server_message(
        {"type": "MODEL_BROADCAST", "sender_id": "B", "bid": "B-1", "age": age},
        [np.array([value], dtype=np.float64)],
    )


@pytest.mark.parametrize(
    "reference_age,expected_weight",
    [(10, 16.0), (7, 11.5), (20, 16.0)],
    ids=["current", "three-updates-stale", "future-reference-clipped"],
)
def test_client_blend_matches_independent_scalar_cases(make_server, reference_age, expected_weight):
    server = make_server()
    server.on_client_update(
        {"client_id": "client", "metrics": {"ref_model_age": reference_age}},
        [np.array([20.0])],
    )
    assert server.global_model_weights[0][0] == pytest.approx(expected_weight)
    assert server.model_age == 11
    assert server.client_update_counts == {"client": 1}
    assert server.client_learning_rates["client"] == 0.01


@pytest.mark.parametrize(
    "own_age,peer_age,phi,expected_weight,expected_age",
    [
        (10, 20, math.log(3), 14.5, 14),
        (20, 10, 2 * math.log(3), 11.5, 20),
        (0, 10, math.log(3) / 10, 14.5, 4),
    ],
    ids=["newer-peer-sigmoid-three-quarters", "older-peer-age-does-not-regress", "zero-age"],
)
def test_peer_blend_and_age_match_independent_scalar_cases(
    make_server, own_age, peer_age, phi, expected_weight, expected_age
):
    server = make_server()
    server.model_age = own_age
    server.spyker_config.sigmoid_phi = phi
    peer_update(server, peer_age, 20.0)
    assert server.global_model_weights[0][0] == pytest.approx(expected_weight)
    assert server.model_age == expected_age
    assert server.get_metrics()["sync_rounds_completed"] == 1
    assert server.get_metrics()["sync_rounds_initiated"] == 0


def test_identical_peer_weights_can_age_the_model_and_dampen_a_pending_update(make_server):
    control, exchanged = make_server(), make_server()
    for server in (control, exchanged):
        server.model_age = 100
        server.server_ages = {"A": 100, "B": 100}
    before = exchanged.global_model_weights[0].copy()
    peer_update(exchanged, 400, 10.0)
    np.testing.assert_array_equal(exchanged.global_model_weights[0], before)
    assert exchanged.model_age == 278
    for server in (control, exchanged):
        server.on_client_update(
            {"client_id": "client", "metrics": {"ref_model_age": 100}},
            [np.array([20.0])],
        )
    assert control.global_model_weights[0][0] == pytest.approx(16.0)
    # The peer exchange adds 178 age units despite unchanged tensors. The pending
    # client contribution therefore has weight 0.6 / 179 = 3 / 895.
    assert exchanged.global_model_weights[0][0] == pytest.approx(10 + 10 * 3 / 895)
    assert exchanged.model_age == 279


@pytest.mark.parametrize("phi,peer_age,expected", [(1000, 0, 10.0), (1000, 20, 16.0)])
def test_extreme_sigmoid_arguments_remain_finite(make_server, phi, peer_age, expected):
    server = make_server()
    server.spyker_config.sigmoid_phi = phi
    peer_update(server, peer_age, 20.0)
    assert server.global_model_weights[0][0] == expected


def test_negative_sigmoid_tail_retains_representable_contributions(make_server):
    server = make_server()
    server.set_initial_weights([np.array([0.0])])
    server.spyker_config.sigmoid_phi = 710
    peer_update(server, 0, 1e300)
    # Independently evaluated 0.6 * sigmoid(-710) * 10^300; exp(710) overflows.
    assert server.global_model_weights[0][0] == pytest.approx(2.68577173540508e-9, abs=1e-20)
    assert server.model_age == 10


@pytest.mark.parametrize(
    "count,average,expected",
    [(1, 2, 0.01), (2, 2, 0.01), (2, 1.81, 0.0005), (2, 1.8, 1e-6), (2, 1, 1e-6)],
)
def test_feedback_restores_base_rate_and_applies_the_floor(make_server, count, average, expected):
    assert make_server()._calculate_decay(count, average, 0.01) == pytest.approx(expected)


@pytest.mark.parametrize("sizes", [(50, 50, 50, 50), (140, 20, 20, 20)])
def test_73_equal_count_waves_match_the_independent_floor_counts(make_server, sizes):
    floor_updates = floor_decisions = 0
    for size in sizes:
        server = make_server()
        for _wave in range(73):
            for index in range(size):
                client = str(index)
                floor_updates += server.client_learning_rates.get(client, 0.01) == 1e-6
                server.on_client_update(
                    {"client_id": client, "metrics": {"ref_model_age": server.model_age}},
                    [np.array([10.0])],
                )
                floor_decisions += server.client_learning_rates[client] == 1e-6
        assert server.total_client_updates_processed == 73 * size
    # 160 floor assignments per noninitial wave. Decisions affect the next fit:
    # 72 decision waves and 71 subsequently delivered floor-update waves.
    assert floor_decisions == 11_520
    assert floor_updates == 11_360


def test_wave_order_changes_client_floor_exposure_without_changing_total(make_server):
    def exposure(orders):
        server = make_server()
        assert server.full_config.training.learning_rate == 0.01
        assert server.spyker_config.decay_beta == 0.05
        assert server.spyker_config.min_learning_rate == 1e-6
        completed_at_floor = dict.fromkeys("ABCD", 0)
        floor_decisions = 0
        for wave, order in enumerate(orders):
            for client in order:
                # The delivered update uses the preceding assignment, not the
                # next assignment produced by this callback.
                used_rate = server.client_learning_rates.get(client, 0.01)
                completed_at_floor[client] += used_rate == 1e-6
                server.on_client_update(
                    {"client_id": client, "metrics": {"ref_model_age": server.model_age}},
                    [np.array([10.0])],
                )
                assigned_rate = server.client_learning_rates[client]
                floor_decisions += assigned_rate == 1e-6
                if wave == 0:
                    assert used_rate == assigned_rate == 0.01
        assert server.client_update_counts == dict.fromkeys("ABCD", 4)
        np.testing.assert_array_equal(server.global_model_weights[0], np.array([10.0]))
        assert floor_decisions == 9
        return completed_at_floor

    # Each later wave floors its first three processed positions. Fixed order
    # repeatedly assigns those positions to A/B/C; rotating order changes who
    # receives the assignments while preserving three floor decisions per wave.
    fixed = exposure(["ABCD"] * 4)
    rotating = exposure(["ABCD", "BCDA", "CDAB", "DABC"])
    assert fixed == {"A": 2, "B": 2, "C": 2, "D": 0}
    assert rotating == {"A": 1, "B": 1, "C": 2, "D": 2}
    assert sum(fixed.values()) == sum(rotating.values()) == 6


@pytest.mark.parametrize("after_sync,expected_delay", [(False, 1.001008), (True, 0.001008)])
def test_token_idle_heartbeat_is_omitted_after_a_completed_exchange(
    make_server, after_sync, expected_delay
):
    server = make_server()
    server.set_token_holder(True)
    server._pass_token(immediate_sync_after_release=after_sync)
    (event,) = server._get_and_clear_events()
    assert event[0] == pytest.approx(expected_delay)
    assert event[3]["data"]["type"] == "TOKEN"
    assert not server.has_token


def test_constructor_keeps_the_current_actor_reference(make_server):
    assert make_server().self_ref is not None
