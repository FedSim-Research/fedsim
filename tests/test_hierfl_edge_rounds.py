import numpy as np
import pytest

from fedsim.engines.hierarchical.edge import EdgeServer
from fedsim.engines.hierarchical.simulation import HierarchicalSimulation
from fedsim.learning import split_partition
from fedsim.simulation.context import SimulationContext
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


@pytest.fixture
def make_edge(local_actor):
    def make(**kwargs):
        link = Network(1, 0, 0, 0)
        specs = {
            "E": ServerSpec("E", "E", Performance(10, 0), {"S": link}, 100, 100),
            "S": ServerSpec("S", "S", Performance(10, 0), {"E": link}, 100, 100),
        }
        context = SimulationContext("orchestrator", {}, specs, seed=1)
        edge = local_actor(EdgeServer, "E", "S", "S", 2, context, **kwargs)
        edge.set_orchestrator("orchestrator")
        edge.context = context
        edge.assigned_client_instances = {"a": "a", "b": "b"}
        edge.on_server_message(
            {"type": "MODEL_SYNC", "model_age": 0, "training_config": {}}, [np.zeros(1)]
        )
        edge._get_and_clear_events()
        return edge

    return make


def report_round(edge, value):
    for client in ("a", "b"):
        edge.on_client_update({"client_id": client, "num_examples": 1}, [np.array([value])])
    return [event[3]["event_type"] for event in edge._get_and_clear_events()]


def test_default_edge_reports_upstream_after_one_round(make_edge):
    assert report_round(make_edge(), 1.0) == ["SERVER_MESSAGE"]


def test_edge_rounds_redispatch_clients_before_reporting(make_edge):
    edge = make_edge(edge_rounds=2)
    assert report_round(edge, 1.0) == ["START_FIT", "START_FIT"]
    np.testing.assert_allclose(edge.global_model_weights[0], [1.0])
    assert report_round(edge, 2.0) == ["SERVER_MESSAGE"]
    assert edge.edge_rounds_done == 0


@pytest.mark.parametrize("rounds", [0, 1.5, True])
def test_invalid_edge_rounds_are_rejected(rounds):
    with pytest.raises(ValueError, match="hierfl_invalid_edge_rounds"):
        HierarchicalSimulation(edge_rounds=rounds)


def test_zero_holdout_trains_on_every_example():
    from datasets import Dataset

    partition = Dataset.from_dict({"label": list(range(10))})
    split = split_partition(partition, 0.0, seed=1)
    assert len(split["train"]) == 10 and len(split["test"]) == 0
    assert len(split_partition(partition, 0.2, seed=1)["test"]) == 2
    with pytest.raises(ValueError, match="local_holdout"):
        split_partition(partition, 1.0, seed=1)
