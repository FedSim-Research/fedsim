import json
from unittest.mock import Mock

import pytest
import ray
import torch
from torch.utils.data import DataLoader

from fedsim.clients import training
from fedsim.clients.actor import VirtualClientActor
from fedsim.engines.hierarchical import edge as hierarchical_edge
from fedsim.engines.spyker import server as spyker_server
from fedsim.persistence.models import Edge, Graph, Node
from fedsim.services.hierfl_simulation_builder import build_hierfl_simulation
from fedsim.services.simulation_validation import validate_start_payload
from fedsim.services.spyker_simulation_builder import build_spyker_simulation
from fedsim.simulation.context import SimulationContext


def topology(architecture):
    graph = Graph(id=123, name="Synthetic", architecture=architecture)
    kinds = {"server": "ServerNode", "clients": "ClientNode"}
    links = [("server", "clients")]
    if architecture == "hierfl":
        kinds["coordinator"] = "SuperServerNode"
        links.append(("coordinator", "server"))
    graph.nodes = [
        Node(
            id=node_id,
            type=kind,
            config_json=json.dumps(
                {
                    "computeFactor": 10,
                    "uploadMbps": 5,
                    "downloadMbps": 20,
                    "count": 2,
                    "type": "workstation",
                }
            ),
            position_json='{"x": 0, "y": 0}',
        )
        for node_id, kind in kinds.items()
    ]
    graph.edges = [
        Edge(
            source_node_id=source,
            target_node_id=target,
            config_json=json.dumps(
                {"pingMs": 10, "jitterMs": 0, "packetloss": 0, "packetlossStddev": 0}
            ),
        )
        for source, target in links
    ]
    return graph


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_builders_expand_client_groups_without_starting_ray(architecture):
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    simulation = builder(
        topology(architecture),
        training_config={"epochs": 1, "lr": 0.01, "batch_size": 8},
        run_time_limit=20,
        seed=42,
        run_id="synthetic-run",
        eval_interval=0,
    )
    assert set(simulation.client_registry) == {"clients-1", "clients-2"}
    assert len(simulation.server_registry) == (2 if architecture == "hierfl" else 1)
    assert simulation.run_id == "synthetic-run"
    assert simulation.seed == 42
    assert str(simulation.graph_id) == "123"
    assert len(simulation.client_map["server"]) == 2
    assert not ray.is_initialized()


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_builders_reject_disconnected_clients(architecture):
    graph = topology(architecture)
    graph.edges = [edge for edge in graph.edges if edge.target_node_id != "clients"]
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    with pytest.raises(ValueError, match="client_requires_single_server_link"):
        builder(graph, training_config={"epochs": 1, "lr": 0.01})


@pytest.mark.parametrize("complete", [False, True])
def test_spyker_requires_direct_links_between_every_pair_of_servers(complete):
    graph = topology("spyker")
    for node_id in ("peer", "third"):
        graph.nodes.append(
            Node(id=node_id, type="ServerNode", config_json=graph.nodes[0].config_json)
        )
    pairs = [("server", "peer"), ("peer", "third")]
    if complete:
        pairs.append(("third", "server"))
    for source, target in pairs:
        graph.edges.append(
            Edge(
                source_node_id=source, target_node_id=target, config_json=graph.edges[0].config_json
            )
        )
    if complete:
        simulation = build_spyker_simulation(graph, training_config={"epochs": 1, "lr": 0.01})
        assert set(simulation.server_registry) == {"server", "peer", "third"}
    else:
        with pytest.raises(ValueError, match="spyker_requires_fully_connected_servers"):
            validate_start_payload("spyker", graph, {"epochs": 1, "lr": 0.01}, None, None)
        with pytest.raises(ValueError, match="spyker_requires_fully_connected_servers"):
            build_spyker_simulation(graph, training_config={"epochs": 1, "lr": 0.01})


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_selected_dataset_and_batch_size_reach_training(monkeypatch, local_actor, architecture):
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    simulation = builder(
        topology(architecture),
        training_config={"epochs": 2, "lr": 0.02, "batch_size": 3},
        dataset_id="ylecun/mnist",
        seed=17,
    )
    client_id, client_config = simulation.client_map["server"][0]
    context = SimulationContext(None, simulation.client_registry, simulation.server_registry)
    samples = [{"img": torch.zeros(3, 32, 32), "label": index % 2} for index in range(8)]
    loader = DataLoader(samples, batch_size=32, shuffle=False)
    load_data = Mock(return_value=(loader, loader))
    batch_lengths = []

    def observe_training(net, batches, epochs, lr, device):
        assert epochs == 2
        assert lr == 0.02
        batch_lengths.extend(len(batch["label"]) for batch in batches)
        return 0.25

    monkeypatch.setattr(training, "load_data", load_data)
    monkeypatch.setattr(training, "train", observe_training)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    client = local_actor(VirtualClientActor, client_id, client_config, context)
    initial_weights = client.inner_client.get_parameters()
    actor_factory = Mock()
    if architecture == "spyker":
        monkeypatch.setattr(spyker_server, "VirtualClientActor", actor_factory)
        server = local_actor(spyker_server.SpykerServer, "server", simulation.config, context)
        server.set_initial_weights(initial_weights)
        server.set_topology({}, "server", [client_id])
    else:
        monkeypatch.setattr(hierarchical_edge, "VirtualClientActor", actor_factory)
        server = local_actor(
            hierarchical_edge.EdgeServer, "server", "coordinator", object(), 1, context
        )
    server.register_clients({client_id: client_config})
    server.set_orchestrator(object())
    if architecture == "spyker":
        events = server.start_simulation()
    else:
        events = server.handle_event(
            {
                "event_type": "SERVER_MESSAGE",
                "trigger_time": 0.0,
                "data": {
                    "type": "MODEL_SYNC",
                    "model_age": 0,
                    "training_config": simulation.super_config,
                },
            },
            direct_refs=initial_weights,
        )
    assert len(events) == 1
    _, _, _, payload, weights = events[0]
    updates = client.handle_event(payload, direct_refs=weights)

    assert batch_lengths == [3, 3, 2]
    load_data.assert_called_once_with(
        client_config["dataset_partition_id"],
        client_config["total_partitions"],
        seed=client_config["seed"],
        dataset_id="ylecun/mnist",
    )
    assert updates[0][3]["data"]["num_examples"] == 8
    assert not ray.is_initialized()


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
@pytest.mark.parametrize("sigma", [None, 0.0, 0.75])
def test_builders_use_configured_runtime_sigma(architecture, sigma):
    graph = topology(architecture)
    if sigma is not None:
        for node in graph.nodes:
            config = json.loads(node.config_json)
            config["performanceSigma"] = sigma
            node.config_json = json.dumps(config)
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    simulation = builder(graph, training_config={"epochs": 1, "lr": 0.01})
    specs = [*simulation.client_registry.values(), *simulation.server_registry.values()]
    assert all(spec.performance_metrics.performance_stddev == (sigma or 0.0) for spec in specs)


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
@pytest.mark.parametrize(
    "field,value",
    [
        ("computeFactor", "NaN"),
        ("computeFactor", "inf"),
        ("performanceSigma", -1),
        ("performanceSigma", "NaN"),
        ("performanceSigma", "inf"),
        ("performanceSigma", "invalid"),
    ],
)
def test_builders_reject_invalid_performance_parameters(architecture, field, value):
    graph = topology(architecture)
    config = json.loads(graph.nodes[0].config_json)
    config[field] = value
    graph.nodes[0].config_json = json.dumps(config)
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    with pytest.raises(ValueError, match=f"{architecture}_invalid_.*_{field}"):
        validate_start_payload(architecture, graph, {"epochs": 1, "lr": 0.01}, None, None)
    with pytest.raises(ValueError, match=f"{architecture}_invalid_.*_{field}"):
        builder(graph, training_config={"epochs": 1, "lr": 0.01})
