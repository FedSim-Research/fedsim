import random
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

from fedsim.clients import actor as client_actor
from fedsim.engines.hierarchical.coordinator import SuperServer
from fedsim.engines.hierarchical.edge import EdgeServer
from fedsim.engines.spyker.server import SpykerServer
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.network_model import estimate_transmission_time
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


@pytest.mark.parametrize(
    "payload_bytes,upload_mbps,download_mbps,loss,latency_ms,expected_seconds",
    [
        (0, 8, 8, 0, 20, 0.02),
        (1_000_000, 8, 8, 0, 0, 1),
        (1_048_576, 8, 8, 0, 0, 1.048576),
        (1_000_000, 2, 8, 0, 0, 4),
        (1_000_000, 8, 2, 0, 0, 4),
        (500_000, 8, 8, 0.5, 20, 1.02),
    ],
)
def test_bytes_and_decimal_mbps_produce_known_transfer_durations(
    payload_bytes, upload_mbps, download_mbps, loss, latency_ms, expected_seconds
):
    sender = ClientSpec("sender", "Sender", Performance(1, 0), upload_mbps, 100)
    receiver = ClientSpec("receiver", "Receiver", Performance(1, 0), 100, download_mbps)
    link = Network(latency_ms, 0, loss, 0)
    duration = estimate_transmission_time(
        sender, receiver, {"link": link}, "link", payload_bytes, rng=random.Random(42)
    )
    assert duration == pytest.approx(expected_seconds)


def test_unit_conversion_preserves_sampled_loss_and_latency():
    sender = ClientSpec("sender", "Sender", Performance(1, 0), 4, 100)
    receiver = ClientSpec("receiver", "Receiver", Performance(1, 0), 100, 8)
    link = Network(20, 3, 0.05, 0.01)
    rng = Mock()
    rng.gauss.side_effect = [0.25, 50]
    duration = estimate_transmission_time(
        sender, receiver, {"link": link}, "link", 1_000_000, rng=rng
    )
    assert duration == pytest.approx(8 / 3 + 0.05)
    assert [call.args for call in rng.gauss.call_args_list] == [(0.05, 0.01), (20, 3)]


@pytest.mark.parametrize(
    "kind,expected_seconds",
    [
        ("coordinator", 1.02),
        ("edge", 1.02),
        ("spyker-model", 1.02),
        ("spyker-token", 0.021),
        ("spyker-empty-model", 0.02),
    ],
)
def test_server_paths_count_tensor_bytes_and_use_explicit_control_message_size(
    local_actor, kind, expected_seconds
):
    link = Network(20, 0, 0, 0)
    specs = {
        name: ServerSpec(name, name, Performance(10, 0), {peer: link}, 8, 8)
        for name, peer in (("A", "B"), ("B", "A"))
    }
    context = SimulationContext("orchestrator", {}, specs, seed=42)
    context.set_server_actor_handles({"A": "A", "B": "B"})
    # Two different dtypes: each tensor contains 500,000 bytes.
    weights = [np.zeros(125_000, dtype=np.float32), np.zeros(62_500, dtype=np.float64)]
    if kind == "coordinator":
        actor = local_actor(SuperServer, "A", weights, 1, {}, context)
        actor.set_edge_servers({"B": "B"})
    elif kind == "edge":
        actor = local_actor(EdgeServer, "A", "B", "B", 1, context)
        actor.global_model_weights = weights
        actor.client_updates_buffer["client"] = (weights, 10)
    else:
        actor = local_actor(SpykerServer, "A", FullConfiguration(), context)
        actor.set_initial_weights([] if kind == "spyker-empty-model" else weights)
    actor.set_orchestrator("orchestrator")

    if kind == "coordinator":
        actor._broadcast_global_model()
    elif kind == "edge":
        actor._aggregate_and_send_upstream()
    else:
        actor._send_server_message(
            "B", "TOKEN" if kind == "spyker-token" else "MODEL_BROADCAST", {}
        )

    delay, target, _, payload, _ = actor._get_and_clear_events()[0]
    assert delay == pytest.approx(expected_seconds)
    assert payload["trigger_time"] == pytest.approx(expected_seconds)
    assert target == "B"


def test_client_download_and_upload_use_their_respective_payload_sizes(monkeypatch, local_actor):
    link = Network(20, 0, 0, 0)
    client = ClientSpec("client", "Client", Performance(10, 0), 2, 8)
    server = ServerSpec("server", "Server", Performance(100, 0), {"client": link}, 8, 4)
    context = SimulationContext(None, {"client": client}, {"server": server}, seed=42)
    request = [np.zeros(1_000_000, dtype=np.uint8)]
    response = [np.zeros(250_000, dtype=np.float64)]  # 2,000,000 bytes.
    monkeypatch.setattr(
        client_actor,
        "TrainingClient",
        lambda **kwargs: SimpleNamespace(
            fit=lambda **kwargs: {"parameters": response, "num_examples": 10, "metrics": {}}
        ),
    )
    actor = local_actor(
        client_actor.VirtualClientActor,
        "client",
        {"dataset_partition_id": 0, "total_partitions": 1, "seed": 42},
        context,
    )
    events = actor.handle_event(
        {
            "event_type": "START_FIT",
            "trigger_time": 7,
            "data": {"server_id": "server", "server_ref": "server", "config": {}},
        },
        direct_refs=request,
    )
    delay, target, _, payload, weights = events[0]
    # 1 second down, 1 second training, 8 seconds up, 20 ms latency per direction.
    assert delay == pytest.approx(10.04)
    assert payload["trigger_time"] == pytest.approx(17.04)
    assert target == "server"
    assert weights is response
