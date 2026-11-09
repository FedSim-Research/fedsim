from unittest.mock import Mock

import numpy as np
import pytest
import torch
from torch.utils.data import DataLoader

from fedsim.clients import actor as client_actor
from fedsim.clients import training
from fedsim.simulation.context import SimulationContext
from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


def test_client_upload_uses_client_upload_and_server_download(monkeypatch, local_actor):
    link = Network(20, 0, 0.0, 0.0)
    client_spec = ClientSpec("client", "Client", Performance(10, 0), 2, 20)
    server_spec = ServerSpec("server", "Server", Performance(100, 0), {"client": link}, 100, 4)
    context = SimulationContext(None, {"client": client_spec}, {"server": server_spec})
    weights = [np.zeros(1024 * 1024, dtype=np.uint8)]
    inner = Mock()
    inner.fit.return_value = {"parameters": weights, "num_examples": 10, "metrics": {}}
    monkeypatch.setattr(client_actor, "TrainingClient", Mock(return_value=inner))
    actor = local_actor(
        client_actor.VirtualClientActor,
        "client",
        {"dataset_partition_id": 0, "total_partitions": 1},
        context,
    )
    updates = actor.handle_event(
        {
            "event_type": "START_FIT",
            "trigger_time": 7.0,
            "data": {"server_id": "server", "server_ref": "server-handle", "config": {}},
        },
        direct_refs=weights,
    )
    # 1 MiB download at min(100, 20) Mbps + upload at min(2, 4) Mbps,
    # one second of training and 20 ms latency in each direction.
    payload_mbits = weights[0].nbytes * 8 / 1_000_000
    expected = payload_mbits / 20 + payload_mbits / 2 + 1 + 0.04
    delay, target, _, event, _ = updates[0]
    assert delay == pytest.approx(expected)
    assert target == "server-handle"
    assert event["trigger_time"] == pytest.approx(7 + expected)
    assert event["data"]["metrics"]["simulation_duration"] == pytest.approx(expected)


def test_nondefault_batch_size_preserves_loader_random_generator(monkeypatch):
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    samples = [{"img": torch.zeros(3, 32, 32), "label": index} for index in range(20)]

    def load_data(*args, **kwargs):
        return DataLoader(
            samples, batch_size=32, shuffle=True, generator=torch.Generator().manual_seed(123)
        ), None

    observed = []

    def observe_training(net, batches, *args):
        assert batches.batch_size == 3
        observed.append([int(label) for batch in batches for label in batch["label"]])
        return 0.1

    monkeypatch.setattr(training, "load_data", load_data)
    monkeypatch.setattr(training, "train", observe_training)
    client = training.TrainingClient(0, 1, seed=123)
    parameters = client.get_parameters()
    for unrelated_seed in [1, 9876]:
        client.trainloader, client.testloader = load_data()
        torch.manual_seed(unrelated_seed)
        client.fit(parameters, {"batch_size": 3})
    assert observed[0] == observed[1]
    assert sorted(observed[0]) == list(range(20))
