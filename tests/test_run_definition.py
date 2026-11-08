import csv
import io
import json
from dataclasses import FrozenInstanceError
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import pytest
import ray

from fedsim.api.routes import simulation as routes
from fedsim.persistence.database import SessionLocal
from fedsim.persistence.models import Edge, Graph, Node, SimulationRun
from fedsim.services import graph_service, simulation_run_queue, simulation_run_store
from fedsim.services.hierfl_simulation_builder import build_hierfl_simulation
from fedsim.services.run_definition import RunDefinition, definition_path, read_archived_definition
from fedsim.services.spyker_simulation_builder import build_spyker_simulation


def topology(architecture):
    prefix = str(uuid4())
    kinds = [("z", "ServerNode"), ("a", "ServerNode"), ("c1", "ClientNode"), ("c2", "ClientNode")]
    links = [("z", "c1"), ("a", "c2")]
    if architecture == "hierfl":
        kinds.append(("root", "SuperServerNode"))
        links.extend([("root", "z"), ("root", "a")])
    else:
        links.append(("z", "a"))
    graph = Graph(
        id=123, name="Snapshot Prüfung", architecture=architecture, metadata_json='{"x": 1}'
    )
    graph.nodes = [
        Node(
            id=f"{prefix}-{name}",
            type=kind,
            config_json=json.dumps(
                {
                    "computeFactor": 10,
                    "performanceSigma": 0,
                    "uploadMbps": 5,
                    "downloadMbps": 20,
                    "count": 1,
                    "type": "workstation",
                }
            ),
            position_json='{"x": 0, "y": 0}',
        )
        for name, kind in kinds
    ]
    graph.edges = [
        Edge(
            source_node_id=f"{prefix}-{a}",
            target_node_id=f"{prefix}-{b}",
            config_json='{"pingMs": 10, "jitterMs": 0, "packetloss": 0, "packetlossStddev": 0}',
        )
        for a, b in links
    ]
    return graph


def definition(graph, training=None, settings=None):
    return RunDefinition.capture(
        {
            graph.architecture: {
                "graph": graph,
                "training_config": training or {"epochs": 1, "lr": 0.01, "batch_size": 3},
                "simulation_settings": settings or {"seed": 42, "seed_set": [42], "gpu_budget": 0},
            }
        }
    )


def persist_graph(graph):
    graph.id = None
    with SessionLocal.begin() as session:
        session.add(graph)
        session.flush()
        graph_id = graph.id
    return graph_id


@pytest.fixture
def queue(monkeypatch):
    queue = simulation_run_queue.SimulationRunQueue()
    monkeypatch.setattr(routes, "run_queue", queue)
    monkeypatch.setattr(queue, "_sync_accuracy_loss_to_loki", Mock())
    monkeypatch.setattr(queue, "_create_accuracy_loss_snapshots", Mock(return_value={}))
    monkeypatch.setattr(simulation_run_queue, "_get_cluster_gpu_capacity", Mock(return_value=0))
    monkeypatch.setattr(simulation_run_store, "ensure_run_points", Mock())
    monkeypatch.setattr(
        simulation_run_store,
        "get_run_progress_info",
        Mock(
            return_value={
                "current_sim_time": 0.0,
                "run_time_limit": 2.0,
            }
        ),
    )
    return queue


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_definition_is_independent_of_graph_and_caller_mutations(architecture):
    graph = topology(architecture)
    settings = {"seed": 42, "seed_set": [42]}
    training = {"epochs": 1, "lr": 0.01}
    captured = definition(graph, training, settings)
    before = captured.to_metadata()
    graph.nodes[0].config_json = '{"changed": true}'
    graph.nodes.reverse()
    graph.edges.clear()
    settings["seed_set"].append(17)
    training["epochs"] = 99
    exposed = captured.to_metadata()
    exposed["definition"]["runs"].clear()
    reconstructed = captured.graph(architecture)
    reconstructed.nodes.clear()
    assert captured.to_metadata() == before
    assert captured.configurations()[architecture]["training_config"]["epochs"] == 1
    assert len(captured.graph(architecture).nodes) == len(
        before["definition"]["runs"][architecture]["graph"]["nodes"]
    )
    with pytest.raises(FrozenInstanceError):
        captured._json = "changed"


def test_hash_ignores_dictionary_key_order_but_preserves_list_order():
    graph = topology("spyker")
    first = definition(graph, training={"epochs": 1, "lr": 0.01})
    for node in graph.nodes:
        node.config_json = json.dumps(dict(reversed(list(json.loads(node.config_json).items()))))
    second = definition(graph, training={"lr": 0.01, "epochs": 1})
    assert first.sha256 == second.sha256
    graph.nodes.reverse()
    third = definition(graph, training={"lr": 0.01, "epochs": 1})
    assert third.sha256 != first.sha256
    assert [node.id for node in third.graph("spyker").nodes] == [node.id for node in graph.nodes]


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_reconstructed_graph_preserves_builder_behavior(architecture):
    graph = topology(architecture)
    captured = definition(graph)
    builder = build_hierfl_simulation if architecture == "hierfl" else build_spyker_simulation
    kwargs = {
        "training_config": {"epochs": 1, "lr": 0.01, "batch_size": 3},
        "seed": 42,
        "eval_interval": 0,
        "run_time_limit": 2,
    }
    original = builder(graph, **kwargs)
    restored = builder(captured.graph(architecture), **kwargs)
    assert original.client_map == restored.client_map
    assert original.client_registry == restored.client_registry
    assert list(original.server_registry) == list(restored.server_registry)
    assert [edge.source_node_id for edge in graph.edges] == [
        edge.source_node_id for edge in captured.graph(architecture).edges
    ]
    assert not ray.is_initialized()


def test_archive_failure_does_not_publish_job(monkeypatch, queue):
    captured = definition(topology("spyker"))
    monkeypatch.setattr(RunDefinition, "archive", Mock(side_effect=OSError("disk full")))
    with pytest.raises(OSError, match="disk full"):
        queue.enqueue(captured)
    assert queue.list_runs() == []
    assert queue._queue.empty()


def test_archive_detects_changed_content(queue):
    job = queue.enqueue(definition(topology("spyker")))
    path = definition_path(job.run_id)
    envelope = json.loads(path.read_text(encoding="utf-8"))
    envelope["definition"]["runs"]["spyker"]["simulation_settings"]["seed"] = 17
    path.write_text(json.dumps(envelope), encoding="utf-8")
    with pytest.raises(ValueError, match="run_definition_checksum_mismatch"):
        read_archived_definition(job.run_id)


def test_atomic_archive_failure_removes_temporary_file(monkeypatch, queue):
    run_id = uuid4()
    monkeypatch.setattr(simulation_run_queue, "uuid4", lambda: run_id)
    monkeypatch.setattr(Path, "replace", Mock(side_effect=OSError("rename failed")))
    with pytest.raises(OSError, match="rename failed"):
        queue.enqueue(definition(topology("spyker")))
    assert not definition_path(str(run_id)).exists()
    assert not definition_path(str(run_id)).with_suffix(".tmp").exists()
    assert queue.list_runs() == []
    assert queue._queue.empty()


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
@pytest.mark.parametrize("edit", ["modify", "delete"])
def test_api_queued_run_uses_captured_graph_after_edit_or_delete(
    api, monkeypatch, queue, architecture, edit
):
    graph_id = persist_graph(topology(architecture))
    response = api.post(
        "/start_simulation",
        json={
            "graph_id": graph_id,
            "training_config": {"epochs": 1, "lr": 0.01, "batch_size": 3},
            "simulation_settings": {
                "seed": 42,
                "gpu_budget": 0,
                "run_time_limit": 2,
                "eval_interval": 0,
            },
        },
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    captured = response.json()["run_metadata"]["run_definition"]
    snapshot = captured["definition"]["runs"][architecture]["graph"]
    assert api.get(f"/runs/{run_id}/export/definition").json() == captured
    if edit == "delete":
        assert graph_service.delete_graph(graph_id)
    else:
        with SessionLocal.begin() as session:
            graph = session.get(Graph, graph_id)
            graph.nodes[0].config_json = '{"computeFactor": 999}'
            graph.name = "Modified after submission"
    seen = []

    def controller(*args, **kwargs):
        seen.append(kwargs)
        return Mock(start=Mock(return_value={"output_filename": None}))

    monkeypatch.setattr(simulation_run_queue, "SimulationController", controller)
    # Any attempt to reload the editor graph during execution must fail this test.
    monkeypatch.setattr(
        graph_service, "get_graph", Mock(side_effect=AssertionError("live graph reload"))
    )
    queue._run_job(run_id)
    assert queue.get(run_id).status == "completed", queue.get(run_id).error
    assert seen[0]["graph"].name == snapshot["name"]
    assert [n.id for n in seen[0]["graph"].nodes] == [n["id"] for n in snapshot["nodes"]]
    assert json.loads(seen[0]["graph"].nodes[0].config_json) == snapshot["nodes"][0]["config"]
    persisted = api.get(f"/runs/{run_id}").json()
    assert persisted["run_metadata"]["run_definition"] == captured
    row = next(csv.DictReader(io.StringIO(api.get(f"/runs/{run_id}/export/csv").text)))
    assert json.loads(row["metadata_json"])["run_definition"] == captured
    assert api.delete(f"/runs/{run_id}").status_code == 204
    assert api.get(f"/runs/{run_id}/export/definition").status_code == 404
    assert not ray.is_initialized()


def test_combined_submission_preserves_both_deleted_graphs_and_requested_settings(
    api, monkeypatch, queue
):
    graph_ids = {arch: persist_graph(topology(arch)) for arch in ("hierfl", "spyker")}
    response = api.post(
        "/start_simulation_both",
        json={
            arch: {
                "graph_id": graph_id,
                "training_config": {"epochs": 1, "lr": 0.01},
                "simulation_settings": {"seed_set": [42, 17], "gpu_budget": 1, "eval_interval": 0},
            }
            for arch, graph_id in graph_ids.items()
        },
    )
    assert response.status_code == 200, response.text
    run_id = response.json()["run_id"]
    captured = response.json()["run_metadata"]["run_definition"]
    for graph_id in graph_ids.values():
        assert graph_service.delete_graph(graph_id)
    monkeypatch.setattr(
        graph_service, "get_graph", Mock(side_effect=AssertionError("live graph reload"))
    )
    seen = []

    def controller(architecture, **kwargs):
        seen.append((architecture, kwargs))
        return Mock(start=Mock(return_value={"output_filename": None}))

    monkeypatch.setattr(simulation_run_queue, "SimulationController", controller)
    queue._run_job(run_id)
    job = queue.get(run_id)
    assert job.status == "completed", job.error
    assert len(seen) == 4
    assert job.definition.to_metadata() == captured
    for architecture, kwargs in seen:
        assert kwargs["graph"].id == graph_ids[architecture]
        assert kwargs["simulation_settings"]["gpu_budget"] == 0
    for architecture in ("hierfl", "spyker"):
        assert job.combined_payload[architecture]["simulation_settings"]["gpu_budget"] == 1
        assert (
            job.result["results_by_architecture"][architecture]["runs"][0]["simulation_settings"][
                "gpu_budget"
            ]
            == 0
        )
    assert read_archived_definition(run_id) == captured
    # The artifact remains readable independently of the in-memory queue.
    monkeypatch.setattr(routes, "run_queue", simulation_run_queue.SimulationRunQueue())
    assert api.get(f"/runs/{run_id}/export/definition").json() == captured
    assert api.get(f"/runs/{run_id}").json()["run_metadata"]["run_definition"] == captured
    assert not ray.is_initialized()


def test_historical_run_without_snapshot_remains_readable_and_deletable(api, queue):
    run_id = f"legacy-{uuid4()}"
    with SessionLocal.begin() as session:
        session.add(
            SimulationRun(
                run_id=run_id,
                architecture="spyker",
                status="completed",
                queued_at=datetime.now(timezone.utc),
                metadata_json='{"graph_id": 1}',
            )
        )
    assert api.get(f"/runs/{run_id}").status_code == 200
    assert api.get(f"/runs/{run_id}/export/definition").status_code == 404
    assert api.delete(f"/runs/{run_id}").status_code == 204


def test_invalid_run_id_cannot_escape_archive_directory(api, queue):
    assert api.get("/runs/not-a-uuid/export/definition").status_code == 404


def test_nonfinite_inputs_are_not_archived(queue):
    graph = topology("spyker")
    graph.metadata_json = '{"invalid": NaN}'
    with pytest.raises(ValueError):
        definition(graph)
    assert queue.list_runs() == []
