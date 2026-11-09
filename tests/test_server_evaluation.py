import csv
import io
import json
import math
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import torch
from sqlalchemy import delete, select
from torch.utils.data import DataLoader

from fedsim import evaluation, learning
from fedsim.engines.spyker.server import SpykerServer
from fedsim.engines.spyker.simulation import SpykerSimulation
from fedsim.persistence.models import EvaluationPoint, SimulationRun
from fedsim.services import (
    controller,
    evaluation_point_store,
    loki_sync_service,
    simulation_run_store,
)
from fedsim.services.simulation_run_queue import _build_series_result
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.telemetry import evaluator as periodic


def fixed_model(predicted_class):
    model = learning.Net(seed=17)
    with torch.no_grad():
        for parameter in model.parameters():
            parameter.zero_()
        model.fc2.bias[predicted_class] = 8
    return model


def common_test_loader():
    samples = [{"img": torch.zeros(3, 32, 32), "label": label} for label in (0, 0, 1)]
    return DataLoader(samples, batch_size=2, shuffle=False)


@pytest.mark.parametrize("batch_size", [1, 2, 3])
def test_evaluation_loss_weights_examples_including_partial_batches(batch_size):
    samples = [
        {"img": torch.tensor(logits), "label": 0} for logits in ([5.0, 0.0], [5.0, 0.0], [0.0, 5.0])
    ]
    loss, accuracy = learning.test(
        torch.nn.Identity(), DataLoader(samples, batch_size=batch_size), torch.device("cpu")
    )
    assert accuracy == pytest.approx(2 / 3)
    assert loss == pytest.approx(5 / 3 + math.log1p(math.exp(-5)))


def test_checkpoints_are_evaluated_individually_on_one_common_loader(monkeypatch, tmp_path):
    paths = {}
    for index, server_id in enumerate(("A", "B")):
        path = tmp_path / f"{server_id}.pth"
        torch.save(fixed_model(index).state_dict(), path)
        paths[server_id] = str(path)
    loader = Mock(return_value=common_test_loader())
    monkeypatch.setattr(evaluation, "load_evaluation_data", loader)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    result = evaluation.evaluate_models(paths, "ylecun/mnist")
    loader.assert_called_once_with("ylecun/mnist", batch_size=32)
    assert result["aggregation"] == "server_macro_mean"
    assert result["server_count"] == 2
    assert result["accuracy"] == pytest.approx(0.5)
    assert result["per_server"]["A"]["accuracy"] == pytest.approx(2 / 3)
    assert result["per_server"]["B"]["accuracy"] == pytest.approx(1 / 3)
    assert result["avg_loss"] == pytest.approx(
        sum(item["avg_loss"] for item in result["per_server"].values()) / 2
    )
    for index, path in enumerate(paths.values()):
        state = torch.load(path, weights_only=True)
        assert state["fc2.bias"].argmax().item() == index


def test_evaluation_normalizes_by_examples_actually_yielded():
    samples = [
        {"img": torch.tensor(logits), "label": 0} for logits in ([5.0, 0.0], [5.0, 0.0], [0.0, 5.0])
    ]
    loss, accuracy = learning.test(
        torch.nn.Identity(), DataLoader(samples, batch_size=2, drop_last=True), torch.device("cpu")
    )
    assert accuracy == 1
    assert loss == pytest.approx(math.log1p(math.exp(-5)), rel=1e-5)


def test_empty_evaluation_dataset_has_a_clear_error():
    with pytest.raises(ValueError, match="evaluation_requires_examples"):
        learning.test(torch.nn.Identity(), DataLoader([]), torch.device("cpu"))


def test_empty_server_evaluation_fails_before_dataset_loading(monkeypatch):
    loader = Mock()
    monkeypatch.setattr(evaluation, "load_evaluation_data", loader)
    with pytest.raises(ValueError, match="evaluation_requires_servers"):
        evaluation.evaluate_models({})
    loader.assert_not_called()


def test_spyker_saves_each_model_with_safe_paths_and_retains_primary_filename(
    monkeypatch, tmp_path
):
    simulation = SpykerSimulation()
    simulation.server_ids = ["../../first", "../../second"]
    states = [fixed_model(index).state_dict() for index in range(2)]
    simulation.spyker_actors_map = {
        server_id: SimpleNamespace(
            get_global_model=SimpleNamespace(
                remote=lambda state=state: [v.numpy() for v in state.values()]
            )
        )
        for server_id, state in zip(simulation.server_ids, states, strict=True)
    }
    monkeypatch.setattr(periodic.ray, "get", lambda value: value)
    primary = tmp_path / "model.pth"
    paths = simulation.save_model(str(primary))
    assert paths == {
        "../../first": str(primary),
        "../../second": str(tmp_path / "model.server-2.pth"),
    }
    for server_id, state in zip(simulation.server_ids, states, strict=True):
        loaded = torch.load(paths[server_id], weights_only=True)
        assert all(torch.equal(loaded[key], expected) for key, expected in state.items())


def test_server_snapshot_contains_matching_weights_progress_and_virtual_time(local_actor):
    context = SimulationContext(None, {}, {})
    server = local_actor(SpykerServer, "A", FullConfiguration(), context)
    server.set_initial_weights([np.array([17.0])])
    server.model_age = 7
    server.current_virtual_time = 12.5
    snapshot = server.get_evaluation_snapshot()
    assert snapshot["metrics"]["model_age"] == 7
    assert snapshot["virtual_time"] == 12.5
    assert snapshot["parameters"][0][0] == 17


@pytest.mark.parametrize("multi_server", [False, True])
def test_periodic_evaluation_persists_server_details_and_schedules_once(
    monkeypatch, local_actor, database, multi_server
):
    targets = {}
    for index, server_id in enumerate(("A", "B") if multi_server else ("A",)):
        snapshot = {
            "parameters": [value.numpy() for value in fixed_model(index).state_dict().values()],
            "metrics": {"model_age": 3 + index},
            "virtual_time": 9 + index,
        }
        targets[server_id] = SimpleNamespace(
            get_evaluation_snapshot=SimpleNamespace(remote=Mock(return_value=snapshot))
        )
    loader = Mock(return_value=common_test_loader())
    monkeypatch.setattr(periodic, "load_evaluation_data", loader)
    monkeypatch.setattr(periodic, "setup_telemetry_logger", lambda run_id: Mock())
    monkeypatch.setattr(periodic.ray, "get", lambda refs: refs)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    run_id = f"periodic-server-details-{multi_server}"
    actor = local_actor(
        periodic.PeriodicEvaluator,
        run_id,
        "1",
        "spyker" if multi_server else "hierarchical",
        targets["A"],
        "orchestrator",
        5,
        target_servers=targets if multi_server else None,
    )
    events = actor.evaluate({"trigger_time": 10})
    assert len(events) == 1
    assert events[0][0] == 5 and events[0][3]["trigger_time"] == 15
    loader.assert_called_once()
    with database.SessionLocal() as session:
        point = session.execute(
            select(EvaluationPoint).where(EvaluationPoint.run_id == run_id)
        ).scalar_one()
        stats = json.loads(point.server_stats_json)
        assert point.round == 3
        if multi_server:
            assert point.accuracy == pytest.approx(0.5)
            assert stats["aggregation"] == "server_macro_mean" and stats["server_count"] == 2
            assert stats["per_server"]["A"]["round"] == 3
            assert stats["per_server"]["B"]["snapshot_virtual_time"] == 10
            assert stats["per_server"]["B"]["accuracy"] == pytest.approx(1 / 3)
        else:
            assert point.accuracy == pytest.approx(2 / 3)
            assert stats == {"model_age": 3}


def test_failed_peer_snapshot_does_not_publish_a_partial_server_mean(monkeypatch, local_actor):
    monkeypatch.setattr(
        periodic, "load_evaluation_data", lambda *args, **kwargs: common_test_loader()
    )
    monkeypatch.setattr(periodic, "setup_telemetry_logger", lambda run_id: Mock())
    persist = Mock()
    monkeypatch.setattr(periodic, "persist_periodic_evaluation", persist)
    first = SimpleNamespace(get_evaluation_snapshot=SimpleNamespace(remote=Mock(return_value={})))
    failed = SimpleNamespace(
        get_evaluation_snapshot=SimpleNamespace(
            remote=Mock(side_effect=RuntimeError("peer unavailable"))
        )
    )
    actor = local_actor(
        periodic.PeriodicEvaluator,
        "failed-peer",
        "1",
        "spyker",
        first,
        None,
        5,
        target_servers={"A": first, "B": failed},
    )
    with pytest.raises(RuntimeError, match="peer unavailable"):
        actor.start()
    persist.assert_not_called()


def test_controller_forwards_all_checkpoints_to_final_evaluation(monkeypatch):
    checkpoints = {"A": "model.pth", "B": "model.server-2.pth"}
    simulation = Mock()
    simulation.save_model.return_value = checkpoints
    result = evaluation.summarize_server_evaluations(
        {"A": {"accuracy": 0.8, "avg_loss": 1}, "B": {"accuracy": 0.4, "avg_loss": 2}}
    )
    evaluate = Mock(return_value=result)
    instance = controller.SimulationController(
        "spyker",
        simulation_settings={"seed": 17, "output_filename": "model.pth", "evaluate_model": True},
    )
    output = instance._run_simulation(lambda: simulation, lambda: evaluate)
    evaluate.assert_called_once_with(checkpoints, "uoft-cs/cifar10")
    assert output["server_checkpoints"] == checkpoints
    assert output["primary_server_id"] == "A"
    assert output["evaluation"]["accuracy"] == pytest.approx(0.6)


def test_api_csv_and_loki_round_trip_keep_server_details_and_legacy_results(
    api, database, monkeypatch
):
    monkeypatch.setattr(
        simulation_run_store,
        "get_run_progress_info",
        lambda *args, **kwargs: {"current_sim_time": 5, "run_time_limit": 10},
    )
    run_id = "server-evaluation-roundtrip"
    evaluated = evaluation.summarize_server_evaluations(
        {"A": {"accuracy": 0.8, "avg_loss": 1}, "B": {"accuracy": 0.4, "avg_loss": 2}}
    )
    paths = {"A": "model.pth", "B": "model.server-2.pth"}
    result = _build_series_result(
        [17],
        [
            {
                "seed": 17,
                "repetition_index": 1,
                "evaluation": evaluated,
                "server_checkpoints": paths,
                "primary_server_id": "A",
            }
        ],
    )
    with database.SessionLocal.begin() as session:
        for identity, stored in (
            (run_id, result),
            ("legacy-server-result", {"evaluation": {"accuracy": 0.7, "avg_loss": 0.9}}),
        ):
            session.add(
                SimulationRun(
                    run_id=identity,
                    architecture="spyker",
                    status="completed",
                    queued_at=datetime.now(timezone.utc),
                    result_json=json.dumps(stored),
                )
            )
    response = api.get(f"/runs/{run_id}")
    assert response.status_code == 200
    assert response.json()["evaluation"]["per_server"] == evaluated["per_server"]
    assert response.json()["server_checkpoints"] == paths
    row = next(csv.DictReader(io.StringIO(api.get(f"/runs/{run_id}/export/csv").text)))
    assert json.loads(row["result_json"])["runs"][0]["server_checkpoints"] == paths
    legacy = api.get("/runs/legacy-server-result")
    assert legacy.status_code == 200 and legacy.json()["evaluation"]["per_server"] is None

    stats = {
        "aggregation": "server_macro_mean",
        "per_server": evaluated["per_server"],
        "server_count": 2,
    }
    assert evaluation_point_store.persist_periodic_evaluation(
        {
            "log_type": "periodic_evaluation",
            "run_id": run_id,
            "architecture": "spyker",
            "virtual_time": 5,
            "round": 3,
            "accuracy": 0.6,
            "loss": 1.5,
            "server_stats": stats,
        }
    )
    post = Mock(return_value=SimpleNamespace(raise_for_status=lambda: None))
    monkeypatch.setattr(loki_sync_service.requests, "post", post)
    assert loki_sync_service.sync_run_to_loki(run_id)
    streams = post.call_args.kwargs["json"]["streams"]
    assert json.loads(streams[0]["values"][0][1])["server_stats"] == stats
    with database.SessionLocal.begin() as session:
        session.execute(delete(EvaluationPoint).where(EvaluationPoint.run_id == run_id))
    get = Mock(
        return_value=SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"status": "success", "data": {"result": streams}},
        )
    )
    monkeypatch.setattr(loki_sync_service.requests, "get", get)
    assert loki_sync_service.reconstruct_from_loki(run_id) == 1
    assert loki_sync_service.reconstruct_from_loki(run_id) == 0
    assert json.dumps(run_id) in get.call_args.kwargs["params"]["query"]
    with database.SessionLocal() as session:
        point = session.execute(
            select(EvaluationPoint).where(EvaluationPoint.run_id == run_id)
        ).scalar_one()
        assert point.round == 3 and json.loads(point.server_stats_json) == stats


def test_loki_reconstruction_keeps_legacy_text_support(database, monkeypatch):
    run_id = "legacy-evaluation-text"
    timestamp = str(int(datetime.now(timezone.utc).timestamp() * 1_000_000_000))
    payload = {
        "status": "success",
        "data": {
            "result": [
                {
                    "stream": {"architecture": "spyker"},
                    "values": [
                        [
                            timestamp,
                            f"[spyker Eval] run_id={run_id} T=5.0s | Acc: 70.00% | Loss: 0.9000",
                        ]
                    ],
                }
            ]
        },
    }
    monkeypatch.setattr(
        loki_sync_service.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: payload
        ),
    )
    assert loki_sync_service.reconstruct_from_loki(run_id) == 1
    with database.SessionLocal() as session:
        point = session.execute(
            select(EvaluationPoint).where(EvaluationPoint.run_id == run_id)
        ).scalar_one()
        assert point.accuracy == 0.7 and point.loss == 0.9 and point.round == 0


def test_legacy_text_does_not_duplicate_a_structured_point_with_a_known_round(
    database, monkeypatch
):
    run_id = "mixed-evaluation-formats"
    assert evaluation_point_store.persist_periodic_evaluation(
        {
            "log_type": "periodic_evaluation",
            "run_id": run_id,
            "architecture": "spyker",
            "virtual_time": 5,
            "round": 3,
            "accuracy": 0.7,
            "loss": 0.9,
            "server_stats": {"model_age": 3},
        }
    )
    timestamp = str(int(datetime.now(timezone.utc).timestamp() * 1_000_000_000))
    payload = {
        "status": "success",
        "data": {
            "result": [
                {
                    "stream": {"architecture": "spyker"},
                    "values": [
                        [
                            timestamp,
                            f"[spyker Eval] run_id={run_id} T=5.0s | Acc: 70.00% | Loss: 0.9000",
                        ]
                    ],
                }
            ]
        },
    }
    monkeypatch.setattr(
        loki_sync_service.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None, json=lambda: payload
        ),
    )
    assert loki_sync_service.reconstruct_from_loki(run_id) == 0
    with database.SessionLocal() as session:
        point = session.execute(
            select(EvaluationPoint).where(EvaluationPoint.run_id == run_id)
        ).scalar_one()
        assert point.round == 3


@pytest.mark.parametrize("structured", [False, True])
def test_loki_reconstruction_excludes_child_run_logs(database, monkeypatch, structured):
    run_id = f"parent-run-{structured}"
    timestamp = str(int(datetime.now(timezone.utc).timestamp() * 1_000_000_000))

    def line(identity, time):
        if structured:
            return json.dumps(
                {
                    "extra_data": {
                        "log_type": "periodic_evaluation",
                        "run_id": identity,
                        "architecture": "spyker",
                        "virtual_time": time,
                        "accuracy": 0.7,
                        "loss": 0.9,
                    }
                }
            )
        return f"[spyker Eval] run_id={identity} T={time}s | Acc: 70.00% | Loss: 0.9000"

    streams = [
        {
            "stream": {"architecture": "spyker"},
            "values": [
                [timestamp, line(f"{run_id}:spyker:17:1", 1)],
                [timestamp, line(run_id, 2)],
                [timestamp, line(f"other-{run_id}", 3)],
            ],
        }
    ]
    monkeypatch.setattr(
        loki_sync_service.requests,
        "get",
        lambda *args, **kwargs: SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"status": "success", "data": {"result": streams}},
        ),
    )
    assert loki_sync_service.reconstruct_from_loki(run_id) == 1
    with database.SessionLocal() as session:
        points = (
            session.execute(
                select(EvaluationPoint).where(EvaluationPoint.run_id.like(f"%{run_id}%"))
            )
            .scalars()
            .all()
        )
        assert [(point.run_id, point.virtual_time) for point in points] == [(run_id, 2)]


def test_raw_log_fetch_keeps_exact_run_in_text_and_json(database, monkeypatch, tmp_path):
    run_id = "parent-run"
    text = f"[spyker Eval] run_id={run_id} T=2s | Acc: 70.00% | Loss: 0.9000"
    structured = json.dumps({"extra_data": {"run_id": run_id}})
    child = f"[spyker Eval] run_id={run_id}:spyker:17:1 T=1s | Acc: 70.00% | Loss: 0.9000"
    child_json = json.dumps({"run_id": f"{run_id}:spyker:17:1"})
    logfile = tmp_path / "worker.out"
    logfile.write_text("\n".join([child, text, child_json, structured]), encoding="utf-8")
    monkeypatch.setattr(loki_sync_service, "_candidate_ray_log_dirs", lambda: [tmp_path])
    assert loki_sync_service.fetch_run_logs(run_id) == f"{text}\n{structured}"

    logfile.unlink()
    get = Mock(
        return_value=SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {
                "status": "success",
                "data": {
                    "result": [
                        {
                            "values": [
                                ["1", child],
                                ["2", text],
                                ["3", child_json],
                                ["4", structured],
                            ]
                        }
                    ]
                },
            },
        )
    )
    monkeypatch.setattr(loki_sync_service.requests, "get", get)
    assert loki_sync_service.fetch_run_logs(run_id) == f"{text}\n{structured}"
    assert json.dumps(run_id) in get.call_args.kwargs["params"]["query"]
