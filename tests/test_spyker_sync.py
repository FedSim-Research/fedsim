import heapq
from itertools import count
from unittest.mock import Mock

import numpy as np
import pytest
import ray

from fedsim.engines.spyker.server import SpykerServer
from fedsim.engines.spyker.simulation import SpykerSimulation
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


@pytest.fixture
def servers(local_actor):
    ids = ("A", "B", "C")
    link = Network(1, 0, 0, 0)
    specs = {
        name: ServerSpec(
            name,
            name,
            Performance(10, 0),
            {peer: link for peer in ids if peer != name},
            1000,
            1000,
        )
        for name in ids
    }
    context = SimulationContext("orchestrator", {}, specs)
    context.set_server_actor_handles({name: name for name in ids})
    result = {}
    for name, weight in zip(ids, (10, 20, 30)):
        server = local_actor(SpykerServer, name, FullConfiguration(), context)
        server.set_topology(specs[name].network_metrics, ids[(ids.index(name) + 1) % 3], [])
        server.set_orchestrator("orchestrator")
        server.set_initial_weights([np.array([weight], dtype=np.float64)])
        server.model_age = 10
        server.server_ages = dict.fromkeys(ids, 10)
        result[name] = server
    return result


def receive(server, sender, bid, weight, age=10):
    server.on_server_message(
        {"type": "MODEL_BROADCAST", "sender_id": sender, "bid": bid, "age": age},
        [np.array([weight], dtype=np.float64)],
    )


def weight(server):
    return float(server.get_global_model()[0][0])


def tokens(server):
    return [
        event for event in server._get_and_clear_events() if event[3]["data"]["type"] == "TOKEN"
    ]


def test_initiator_aggregates_each_peer_before_releasing_token(servers):
    server = servers["A"]
    server.set_token_holder(True)
    server._broadcast_model_to_all()
    bid = server.current_bid
    server._get_and_clear_events()

    receive(server, "B", bid, 20)
    assert weight(server) == pytest.approx(13)
    assert server.ongoing_sync and server.has_token
    assert not tokens(server)

    receive(server, "B", bid, 200)
    assert weight(server) == pytest.approx(13)
    assert server.ongoing_sync and server.has_token
    assert not tokens(server)

    receive(server, "C", bid, 30)
    assert weight(server) == pytest.approx(18.1)
    assert not server.ongoing_sync and not server.has_token
    assert server.current_bid == ""
    assert [event[1] for event in tokens(server)] == ["B"]

    receive(server, "C", bid, 300)
    assert weight(server) == pytest.approx(18.1)
    assert not server._get_and_clear_events()
    metrics = server.get_metrics()
    assert metrics["sync_rounds_initiated"] == 1
    assert metrics["sync_rounds_completed"] == 1
    assert metrics["peer_models_aggregated"] == 2


@pytest.mark.parametrize(
    "first,first_weight,second,second_weight,after_first,after_second",
    [("A", 10, "C", 30, 17, 20.9), ("C", 30, "A", 10, 23, 19.1)],
    ids=["initiator-first", "peer-first"],
)
def test_participant_broadcasts_snapshot_once_and_aggregates_both_peers(
    servers, first, first_weight, second, second_weight, after_first, after_second
):
    server = servers["B"]
    server.age_at_last_sync = 2
    receive(server, first, "A-round", first_weight)
    events = server._get_and_clear_events()
    assert len(events) == 2
    assert {event[1] for event in events} == {"A", "C"}
    assert all(float(event[4][0][0]) == 20 for event in events)
    assert weight(server) == pytest.approx(after_first)
    assert server.age_at_last_sync == 10

    receive(server, first, "A-round", 100)
    assert weight(server) == pytest.approx(after_first)
    assert not server._get_and_clear_events()

    receive(server, second, "A-round", second_weight)
    assert weight(server) == pytest.approx(after_second)
    assert not server._get_and_clear_events()


@pytest.mark.parametrize("sender", ["A", "unknown"])
def test_self_and_unknown_senders_cannot_complete_a_sync(servers, sender):
    server = servers["A"]
    server.set_token_holder(True)
    server._broadcast_model_to_all()
    server._get_and_clear_events()
    receive(server, sender, server.current_bid, 999)
    assert weight(server) == 10
    assert server.has_token and server.ongoing_sync
    assert not server._get_and_clear_events()
    receive(server, "B", server.current_bid, 20)
    assert server.has_token and server.ongoing_sync
    assert not tokens(server)


def test_round_ids_are_unique_when_model_age_does_not_change(servers):
    server = servers["A"]
    server.set_token_holder(True)
    server._broadcast_model_to_all()
    previous_bid = server.current_bid
    receive(server, "B", previous_bid, 20)
    receive(server, "C", previous_bid, 30)
    assert server.model_age == 10

    server.set_token_holder(True)
    server._broadcast_model_to_all()
    assert server.current_bid != previous_bid
    server._get_and_clear_events()
    receive(server, "B", previous_bid, 200)
    assert server.has_token and server.ongoing_sync
    assert not server._get_and_clear_events()


def test_peer_age_knowledge_does_not_regress(servers):
    server = servers["B"]
    server.server_ages["A"] = 20
    receive(server, "A", "late-round", 10, age=5)
    assert server.server_ages["A"] == 20
    assert server.server_ages["B"] == server.model_age


@pytest.mark.parametrize("reverse_ties", [False, True])
@pytest.mark.parametrize("slow_initiator_link", [False, True])
def test_three_server_exchange_delivers_all_six_models(reverse_ties, slow_initiator_link, servers):
    if slow_initiator_link:
        registry = servers["A"].context.server_registry
        registry["A"].network_metrics["B"] = Network(30, 0, 0, 0)
        registry["B"].network_metrics["A"] = Network(30, 0, 0, 0)
    leader = servers["A"]
    leader.set_token_holder(True)
    leader._broadcast_model_to_all()
    pending = []
    sequence = count()
    arrivals = {name: [] for name in servers}
    token_events = []

    def enqueue(events):
        for event in events:
            order = next(sequence)
            heapq.heappush(
                pending, (event[3]["trigger_time"], -order if reverse_ties else order, event)
            )

    enqueue(leader._get_and_clear_events())
    while pending:
        _, _, event = heapq.heappop(pending)
        _, target, _, payload, refs = event
        if payload["data"]["type"] == "TOKEN":
            token_events.append(event)
            continue
        arrivals[target].append(payload["data"]["sender_id"])
        enqueue(servers[target].handle_event(payload, direct_refs=refs))

    assert arrivals["B"] == (["C", "A"] if slow_initiator_link else ["A", "C"])
    assert arrivals["C"] == ["A", "B"]
    assert set(arrivals["A"]) == {"B", "C"}
    assert weight(leader) == pytest.approx(18.1 if arrivals["A"][0] == "B" else 17.2)
    assert weight(servers["B"]) == pytest.approx(19.1 if slow_initiator_link else 20.9)
    assert weight(servers["C"]) == pytest.approx(22.8)
    assert len(token_events) == 1 and token_events[0][1] == "B"
    assert sum(server.has_token for server in servers.values()) == 0  # Token is in transit.
    for name, server in servers.items():
        metrics = server.get_metrics()
        assert metrics["sync_rounds_initiated"] == int(name == "A")
        assert metrics["sync_rounds_completed"] == 1
        assert metrics["peer_models_aggregated"] == 2
    assert not ray.is_initialized()


@pytest.mark.parametrize("next_peer", [None, "A"])
def test_single_server_starts_without_self_messages(local_actor, next_peer):
    spec = ServerSpec("A", "A", Performance(10, 0), {}, 1000, 1000)
    context = SimulationContext("orchestrator", {}, {"A": spec})
    context.set_server_actor_handles({"A": "A"})
    server = local_actor(SpykerServer, "A", FullConfiguration(), context)
    server.set_topology({}, next_peer, [])
    server.set_orchestrator("orchestrator")
    server.set_initial_weights([np.array([10.0])])
    server.set_token_holder(True)
    server.model_age = 1000  # Even a synchronization threshold must not open a lone round.
    server.server_ages["A"] = 1000
    assert server.start_simulation() == []
    assert not server.ongoing_sync
    server._pass_token()
    assert server.has_token
    assert not server._get_and_clear_events()
    assert server.get_metrics()["sync_rounds_initiated"] == 0
    assert server.get_metrics()["sync_rounds_completed"] == 0
    assert server.get_metrics()["peer_models_aggregated"] == 0


@pytest.mark.parametrize("self_link", [False, True])
def test_single_server_network_has_no_token_successor(monkeypatch, self_link):
    simulation = SpykerSimulation()
    network = {"A": Network(1, 0, 0, 0)} if self_link else {}
    simulation.add_server("A", "A", Performance(10, 0), network, 1000, 1000)
    actor = Mock()
    simulation.spyker_actors_map = {"A": actor}
    monkeypatch.setattr(ray, "get", lambda value: value)
    simulation._configure_network()
    assert actor.set_topology.remote.call_args.kwargs["next_token_peer"] is None
    assert actor.set_topology.remote.call_args.kwargs["peer_connections"] == {}


def test_engine_rejects_missing_peer_links_before_starting_ray(monkeypatch):
    from fedsim.engines.spyker import simulation as spyker_simulation

    simulation = SpykerSimulation()
    for server_id in ("A", "B"):
        simulation.add_server(server_id, server_id, Performance(10, 0), {}, 1000, 1000)
    initialize = Mock(side_effect=AssertionError("Invalid topology must not start Ray"))
    monkeypatch.setattr(spyker_simulation, "ensure_ray_initialized", initialize)
    with pytest.raises(ValueError, match="spyker_requires_fully_connected_servers"):
        simulation.build()
    initialize.assert_not_called()


def test_duplicate_cache_is_bounded_and_keeps_the_active_round(servers):
    server = servers["A"]
    server.MAX_BROADCAST_CACHE = 2
    server.set_token_holder(True)
    server._broadcast_model_to_all()
    active_bid = server.current_bid
    server._get_and_clear_events()
    for index in range(5):
        receive(server, "B", f"delayed-{index}", 20)
        server._get_and_clear_events()
        assert len(server._sync_participants) <= 2
        assert active_bid in server._sync_participants
    before = weight(server)
    receive(server, "B", "delayed-4", 200)
    assert weight(server) == before
    assert not server._get_and_clear_events()


def message_types(server):
    return [event[3]["data"]["type"] for event in server._get_and_clear_events()]


def test_age_announcements_are_off_by_default(servers):
    server = servers["B"]
    server.model_age = 30
    server._announce_age_if_drifting()
    assert not message_types(server)


def test_drifting_server_without_token_announces_age_once_per_epoch(servers):
    server = servers["B"]
    server.spyker_config.age_announcements = True
    server.model_age = 30
    server._announce_age_if_drifting()
    assert message_types(server) == ["AGE", "AGE"]
    server._announce_age_if_drifting()
    assert not message_types(server)
    server._remember_sync("next")
    server._announce_age_if_drifting()
    assert message_types(server) == ["AGE", "AGE"]


def test_token_holder_starts_sync_on_age_announcement(servers):
    holder = servers["A"]
    holder.has_token = True
    holder.on_server_message({"type": "AGE", "sender_id": "B", "age": 30})
    assert holder.ongoing_sync
    assert "MODEL_BROADCAST" in message_types(holder)


def test_incomplete_sync_releases_token_after_timeout(servers):
    holder = servers["A"]
    holder.spyker_config.sync_timeout = 2.0
    holder.has_token = True
    holder._broadcast_model_to_all()
    assert "SYNC_TIMEOUT" in message_types(holder)
    holder.on_server_message({"type": "SYNC_TIMEOUT", "sender_id": "A", "bid": "stale"})
    assert holder.ongoing_sync
    holder.on_server_message({"type": "SYNC_TIMEOUT", "sender_id": "A", "bid": holder.current_bid})
    assert not holder.ongoing_sync and not holder.has_token
    assert holder.get_metrics()["sync_timeouts"] == 1
    assert message_types(holder) == ["TOKEN"]
