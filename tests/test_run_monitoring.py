"""Keep job/repetition identity consistent across monitoring and completion."""

import json
import re
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest

from fedsim.persistence.models import Graph, SimulationRun
from fedsim.services import evaluation_point_store as points
from fedsim.services import loki_sync_service, simulation_run_queue, simulation_run_store
from fedsim.services.run_definition import RunDefinition


def point(identity, architecture="spyker", time=10, timestamp=None):
    assert points.persist_periodic_evaluation(
        {
            "log_type": "periodic_evaluation",
            "run_id": identity,
            "architecture": architecture,
            "virtual_time": time,
            "round": 1,
            "accuracy": 0.5,
            "loss": 1.25,
            "server_stats": {"per_server": {"A": {"peer_models_aggregated": 2}}},
        },
        timestamp_real=timestamp,
    )


@pytest.mark.parametrize("combined", [False, True])
def test_parent_queries_resolve_only_recorded_repetitions(database, api, combined):
    parent = str(uuid4())
    first, second = f"{parent}:spyker:42:1", f"{parent}:hierfl:42:1"
    series = {"runs": [{"run_id": first}, {"run_id": second}]}
    result = (
        {
            "results_by_architecture": {
                "spyker": {"runs": [{"run_id": first}]},
                "hierfl": {"runs": [{"run_id": second}]},
            }
        }
        if combined
        else series
    )
    finished = datetime.now(timezone.utc)
    with database.SessionLocal.begin() as session:
        session.add(
            SimulationRun(
                run_id=parent,
                architecture="both" if combined else "spyker",
                status="completed",
                queued_at=finished - timedelta(minutes=1),
                finished_at=finished,
                result_json=json.dumps(result),
            )
        )
    before = (finished - timedelta(seconds=1)).isoformat()
    point(first, timestamp=before)
    point(second, "hierarchical", timestamp=before)
    point(first, time=20, timestamp=(finished + timedelta(seconds=1)).isoformat())
    point(first + "-unrecorded", timestamp=before)
    exact = "^" + re.escape(parent) + "$"
    assert set(points.get_matching_run_ids(exact)) == {parent, first, second}
    rows = points.get_evaluation_rows(exact)
    assert {row["run_id"] for row in rows} == {first, second}
    assert len(rows) == 2
    assert points.get_evaluation_rows("^" + re.escape(first) + "$")[0]["run_id"] == first
    assert len(points.get_evaluation_rows(exact, architecture_regex="^spyker$")) == 1
    assert points.get_evaluation_rows(exact, start_ms=int(finished.timestamp() * 1000)) == []
    response = api.post(
        "/grafana-json/query",
        json={"targets": [{"target": "evaluation_timeseries", "payload": {"run_id": exact}}]},
    )
    assert response.status_code == 200
    assert len(response.json()[0]["rows"]) == 2


@pytest.mark.parametrize("combined", [False, True])
def test_queue_syncs_exact_repetition_ids_for_single_and_both_jobs(monkeypatch, combined):
    parent = str(uuid4())
    repetitions = [{"run_id": parent + ":spyker:42:1"}, {"run_id": parent + ":spyker:43:2"}]
    result = {"runs": repetitions}
    if combined:
        result = {
            "results_by_architecture": {
                "spyker": result,
                "hierfl": {"runs": [{"run_id": parent + ":hierfl:42:1"}]},
            }
        }
    sync = Mock(return_value=True)
    monkeypatch.setattr(simulation_run_queue, "sync_run_to_loki", sync)
    simulation_run_queue.SimulationRunQueue()._sync_accuracy_loss_to_loki(
        SimpleNamespace(run_id=parent), result
    )
    expected = points.evaluation_run_ids(parent, result)[1:]
    assert [call.args[0] for call in sync.call_args_list] == expected
    sync.reset_mock()
    simulation_run_queue.SimulationRunQueue()._sync_accuracy_loss_to_loki(
        SimpleNamespace(run_id=parent), {}
    )
    sync.assert_called_once_with(parent)


def test_loki_accepts_child_points_without_a_synthetic_job_record(database, monkeypatch):
    child = str(uuid4()) + ":spyker:42:1"
    timestamp = "2026-11-13T14:00:00+02:00"
    point(child, timestamp=timestamp)
    with database.SessionLocal() as session:
        assert session.get(SimulationRun, child) is None
    post = Mock(return_value=SimpleNamespace(raise_for_status=lambda: None))
    monkeypatch.setattr(loki_sync_service.requests, "post", post)
    assert loki_sync_service.sync_run_to_loki(child)
    stream = post.call_args.kwargs["json"]["streams"][0]
    assert stream["stream"]["run_id"] == child
    expected_ns = int(datetime(2026, 11, 13, 12, tzinfo=timezone.utc).timestamp() * 1_000_000_000)
    assert int(stream["values"][0][0]) == expected_ns
    assert (
        json.loads(stream["values"][0][1])["server_stats"]["per_server"]["A"][
            "peer_models_aggregated"
        ]
        == 2
    )
    assert not loki_sync_service.sync_run_to_loki(str(uuid4()))


def test_loki_parent_sync_keeps_the_recorded_child_identity(database, monkeypatch):
    parent = str(uuid4())
    child = parent + ":spyker:42:1"
    with database.SessionLocal.begin() as session:
        session.add(
            SimulationRun(
                run_id=parent,
                architecture="spyker",
                status="completed",
                queued_at=datetime.now(timezone.utc),
                result_json=json.dumps({"runs": [{"run_id": child}]}),
            )
        )
    point(child)
    post = Mock(return_value=SimpleNamespace(raise_for_status=lambda: None))
    monkeypatch.setattr(loki_sync_service.requests, "post", post)
    assert loki_sync_service.sync_run_to_loki(parent)
    streams = post.call_args.kwargs["json"]["streams"]
    assert len(streams) == 1
    assert streams[0]["stream"]["run_id"] == child
    assert json.loads(streams[0]["values"][0][1])["run_id"] == child


def test_monitoring_ranges_interpret_sqlite_times_as_utc(database):
    parent = str(uuid4())
    with database.SessionLocal.begin() as session:
        session.add(
            SimulationRun(
                run_id=parent,
                architecture="spyker",
                status="completed",
                queued_at=datetime.now(timezone.utc),
            )
        )
    point(parent, timestamp="2026-11-13T14:00:00+02:00")
    expected_ms = int(datetime(2026, 11, 13, 12, tzinfo=timezone.utc).timestamp() * 1000)
    rows = points.get_evaluation_rows(
        "^" + re.escape(parent) + "$", start_ms=expected_ms, end_ms=expected_ms
    )
    assert len(rows) == 1


@pytest.mark.parametrize("failed", [False, True])
def test_terminal_status_is_persisted_before_becoming_visible(database, monkeypatch, failed):
    queue = simulation_run_queue.SimulationRunQueue()
    graph = Graph(id=123, name="lifecycle test", architecture="spyker")
    definition = RunDefinition.capture(
        {
            "spyker": {
                "graph": graph,
                "simulation_settings": {"seed": 42, "seed_set": [42], "run_time_limit": 1},
            }
        }
    )
    job = queue.enqueue(definition)
    monkeypatch.setattr(
        queue,
        "_run_architecture_series",
        Mock(
            side_effect=ValueError("training failed") if failed else None,
            return_value={"runs": [{"run_id": job.run_id + ":spyker:42:1"}]},
        ),
    )
    monkeypatch.setattr(queue, "_sync_accuracy_loss_to_loki", Mock())
    monkeypatch.setattr(queue, "_create_accuracy_loss_snapshots", Mock(return_value={}))
    monkeypatch.setattr(
        simulation_run_store,
        "get_run_progress_info",
        lambda *a, **kw: {"current_sim_time": 1, "run_time_limit": 1},
    )
    persist = simulation_run_store.persist_final_run
    seen = []

    def check_order(terminal):
        assert queue.get(job.run_id).status == "running"
        assert terminal.status == ("failed" if failed else "completed")
        persist(terminal)
        assert simulation_run_store.export_run_to_csv(job.run_id) is not None
        seen.append(terminal.status)

    monkeypatch.setattr(simulation_run_store, "persist_final_run", check_order)
    queue._run_job(job.run_id)
    assert seen == ["failed" if failed else "completed"]
    assert queue.get(job.run_id).status == seen[0]


def test_malformed_optional_legacy_fields_do_not_invent_child_ids():
    assert points.evaluation_run_ids("parent", {"runs": 123, "results_by_architecture": "bad"}) == [
        "parent"
    ]
