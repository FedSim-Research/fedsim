import json

import pytest
import ray

from fedsim.persistence.models import Edge, Graph, Node
from fedsim.services.hierfl_simulation_builder import build_hierfl_simulation
from fedsim.services.spyker_simulation_builder import build_spyker_simulation


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
