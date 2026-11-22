"""Campaign orchestration tests; simulated results are not experiment evidence."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from uuid import uuid4

import pytest
import requests
from pydantic import ValidationError

from fedsim.experiments import campaign
from fedsim.persistence.models import SimulationRun
from fedsim.services import evaluation_point_store, simulation_run_queue

CONFIG = Path(__file__).resolve().parents[1] / "experiments" / "local-pilot.json"


def config(**changes):
    return campaign.CampaignConfig.model_validate(
        {
            **json.loads(CONFIG.read_text()),
            **changes,
        }
    )


def exchange_details():
    return {
        f"server-{i}": {
            "server_stats": {
                "sync_rounds_initiated": int(i == 0),
                "sync_rounds_completed": 1,
                "peer_models_aggregated": 2,
            }
        }
        for i in range(3)
    }


def old_format_config(cfg):
    # What model_dump(exclude_none=True) produced before client_runtime_sigma existed.
    dumped = cfg.model_dump(exclude_none=True)
    del dumped["client_runtime_sigma"]
    return dumped


def test_plan_has_matched_inputs_unique_outputs_and_alternating_order():
    plan = campaign.build_plan(config(), "test-campaign")
    assert len(plan["cases"]) == 12
    assert [c["architecture"] for c in plan["cases"][:4]] == [
        "hierfl",
        "spyker",
        "spyker",
        "hierfl",
    ]
    outputs = []
    for first, second in zip(plan["cases"][::2], plan["cases"][1::2], strict=True):
        clients = []
        for case in (first, second):
            nodes = [n for n in case["graph"]["nodes"] if n["type"] == "ClientNode"]
            clients.append([n["data"]["config"] for n in nodes])
            outputs.append(case["request"]["simulation_settings"]["output_filename"])
        assert clients[0] == clients[1]
        assert sum(n["count"] for n in clients[0]) == 6
        assert first["request"]["training_config"] == second["request"]["training_config"]
        a = dict(first["request"]["simulation_settings"])
        b = dict(second["request"]["simulation_settings"])
        a.pop("output_filename")
        b.pop("output_filename")
        assert a == b
    assert len(set(outputs)) == 12
    assert campaign.build_plan(config(), "test-campaign") == plan


@pytest.mark.parametrize(
    "changes",
    [
        {"seeds": []},
        {"seeds": [42, 42]},
        {"seeds": [True]},
        {"scenarios": {"balanced": [2, 2], "imbalanced": [4, 1]}},
        {"scenarios": {"balanced": [2, 2], "imbalanced": [1, 1, 2]}},
        {"scenarios": {"../unsafe": [2, 2]}},
        {"scenarios": {"empty": []}},
        {"eval_interval": 61},
        {"run_time_limit": float("nan")},
    ],
)
def test_invalid_campaigns_are_rejected(changes):
    with pytest.raises(ValidationError):
        config(**changes)


def test_plan_cli_is_offline_and_refuses_existing_output(tmp_path, monkeypatch):
    monkeypatch.setattr(requests, "Session", Mock(side_effect=AssertionError("HTTP forbidden")))
    output = tmp_path / "preview"
    args = ["plan", "--config", str(CONFIG), "--output", str(output)]
    campaign.main(args)
    assert len(json.loads((output / "plan.json").read_text())["cases"]) == 12
    with pytest.raises(FileExistsError):
        campaign.main(args)


def test_backend_provenance_must_match_the_archived_source():
    source = {"source_commit": "a" * 40, "uv_lock_sha256": "b" * 64}
    environment = {
        **source,
        **{
            key: {"recorded": "value"}
            for key in ("runtime_versions", "hardware", "resource_budget", "dataset_provenance")
        },
    }
    campaign._validate_environment(environment, source)
    with pytest.raises(ValueError, match="source_commit"):
        campaign._validate_environment({**environment, "source_commit": "c" * 40}, source)
    with pytest.raises(ValueError, match="dataset_provenance"):
        campaign._validate_environment({**environment, "dataset_provenance": {}}, source)


def test_campaign_round_trip_uses_real_graph_and_export_routes(
    api, database, monkeypatch, tmp_path
):
    states = {}
    root = tmp_path / "models"
    root.mkdir()

    def enqueue(definition):
        identity = str(uuid4())
        architecture = definition.architecture
        definition.archive(identity)
        frozen = definition.configurations()[architecture]
        filename = frozen["simulation_settings"]["output_filename"]
        model = root / filename
        model.parent.mkdir(parents=True)
        model.write_bytes(b"checkpoint fixture, not trained weights")
        backend_path = "/var/lib/fedsim/models/" + filename
        child = f"{identity}:{architecture}:42:1"
        evaluation = {"accuracy": 0.5, "avg_loss": 1.0}
        result = {
            "output_filename": backend_path,
            "evaluation": evaluation,
            "runs": [{"run_id": child, "seed": 42, "evaluation": evaluation}],
        }
        if architecture == "spyker":
            result["server_checkpoints"] = {f"server-{i}": backend_path for i in range(3)}
            evaluation.update(
                aggregation="server_macro_mean",
                server_count=3,
                per_server={f"server-{i}": {"accuracy": 0.5, "avg_loss": 1.0} for i in range(3)},
            )
        state = {"run_id": identity, "architecture": architecture, "status": "completed", **result}
        states[identity] = state
        with database.SessionLocal.begin() as session:
            session.add(
                SimulationRun(
                    run_id=identity,
                    architecture=architecture,
                    status="completed",
                    queued_at=datetime.now(timezone.utc),
                    result_json=json.dumps(result),
                )
            )
        for run_id in (child, child + "-unrelated"):
            assert evaluation_point_store.persist_periodic_evaluation(
                {
                    "log_type": "periodic_evaluation",
                    "run_id": run_id,
                    "architecture": architecture,
                    "virtual_time": 60,
                    "round": 0,
                    "accuracy": 0.5,
                    "loss": 1,
                    "server_stats": {"per_server": exchange_details()},
                }
            )
        return SimpleNamespace(run_id=identity, to_api_dict=lambda: state)

    monkeypatch.setattr(simulation_run_queue.run_queue, "enqueue", enqueue)
    monkeypatch.setattr(simulation_run_queue.run_queue, "get_run_api", states.get)
    plan = campaign.build_plan(
        config(phase="calibration", seeds=[42], scenarios={"balanced": [2, 2, 2]}), str(uuid4())
    )
    output = tmp_path / "archive"
    output.mkdir()
    campaign._write_json(output / "plan.json", plan)

    # Adapt the HTTP client to avoid passing network timeouts to TestClient.
    def request(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return api.request(method, url, **kwargs)

    campaign.execute_plan(
        plan,
        output,
        str(api.base_url),
        client=SimpleNamespace(request=request),
        checkpoint_root=root,
    )
    execution = json.loads((output / "execution.json").read_text())
    assert execution["status"] == "completed"
    assert len(execution["cases"]) == 2
    for case in plan["cases"]:
        folder = output / case["key"]
        points = json.loads((folder / "evaluations.json").read_text())
        assert len(points) == 1 and points[0]["run_id"].endswith(":42:1")
        assert points[0]["server_stats"]["per_server"] == exchange_details()
        assert (
            folder / "checkpoint-1.pth"
        ).read_bytes() == b"checkpoint fixture, not trained weights"
        frozen = json.loads((folder / "definition.json").read_text())
        campaign._check_definition(frozen, case)
        frozen["definition"]["runs"][case["architecture"]]["training_config"]["epochs"] = 999
        with pytest.raises(ValueError, match="checksum"):
            campaign._check_definition(frozen, case)
    checksums = json.loads((output / "checksums.json").read_text())
    assert all(
        hashlib.sha256((output / name).read_bytes()).hexdigest() == sha
        for name, sha in checksums.items()
    )
    assert api.get("/runs/unknown-campaign/export/evaluations").status_code == 404

    review = tmp_path / "review.json"
    decision = {
        "pilot_archive": "archive",
        "run_time_limit": 60,
        "eval_interval": 20,
        "rationale": "Synthetic orchestration fixture, not a scientific decision.",
    }
    campaign._write_json(review, decision)
    approved = campaign._calibration_review(review, config())
    assert approved["pilot_campaign_id"] == plan["campaign_id"]
    assert approved["pilot_archive"] == str(output.resolve())
    # A pilot archived before the runtime noise field existed must still compare equal.
    old = json.loads((output / "plan.json").read_text())
    old["config"] = old_format_config(
        config(phase="calibration", seeds=[42], scenarios={"balanced": [2, 2, 2]})
    )
    campaign._write_json(output / "plan.json", old)
    checksums["plan.json"] = hashlib.sha256((output / "plan.json").read_bytes()).hexdigest()
    campaign._write_json(output / "checksums.json", checksums)
    assert (
        campaign._calibration_review(review, config())["pilot_campaign_id"] == plan["campaign_id"]
    )
    # The earlier v1 format also omitted all optional Spyker policy defaults.
    old["config"]["spyker_config"] = campaign._comparable_spyker_parameters(
        old["config"]["spyker_config"]
    )
    for case in old["cases"]:
        if case["request"]["spyker_config"] is not None:
            case["request"]["spyker_config"] = campaign._comparable_spyker_parameters(
                case["request"]["spyker_config"]
            )
    campaign._write_json(output / "plan.json", old)
    checksums["plan.json"] = hashlib.sha256((output / "plan.json").read_bytes()).hexdigest()
    campaign._write_json(output / "checksums.json", checksums)
    assert (
        campaign._calibration_review(review, config())["pilot_campaign_id"] == plan["campaign_id"]
    )
    old["config"]["client_runtime_sigma"] = 0.0
    campaign._write_json(output / "plan.json", old)
    checksums["plan.json"] = hashlib.sha256((output / "plan.json").read_bytes()).hexdigest()
    campaign._write_json(output / "checksums.json", checksums)
    assert (
        campaign._calibration_review(review, config())["pilot_campaign_id"] == plan["campaign_id"]
    )
    with pytest.raises(ValueError, match="decision_mismatch"):
        campaign._calibration_review(review, config(run_time_limit=120))
    network = json.loads((CONFIG.parent / "network-sensitivity.json").read_text())["network"]
    with pytest.raises(ValueError, match="conditions_mismatch"):
        campaign._calibration_review(review, config(network=network))
    parameters = config().spyker_config.model_dump()
    with pytest.raises(ValueError, match="conditions_mismatch"):
        campaign._calibration_review(review, config(spyker_config={**parameters, "h_intra": 8}))
    campaign._write_json(review, {**decision, "rationale": "  "})
    with pytest.raises(ValueError, match="requires_rationale"):
        campaign._calibration_review(review, config())
    campaign._write_json(review, decision)
    artifact = output / plan["cases"][0]["key"] / "checkpoint-1.pth"
    artifact.write_bytes(b"changed after collection")
    with pytest.raises(ValueError, match="checksum_mismatch"):
        campaign._calibration_review(review, config())


def test_submission_timeout_is_not_retried_and_leaves_a_journal(tmp_path):
    client = Mock()
    client.request.side_effect = [
        SimpleNamespace(
            raise_for_status=lambda: None,
            json=lambda: {"paths": {"/runs/{run_id}/export/evaluations": {}}},
        ),
        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"graph_id": 1}),
        SimpleNamespace(raise_for_status=lambda: None, json=lambda: {}),
        requests.Timeout("server may have accepted submission"),
    ]
    plan = campaign.build_plan(config(seeds=[42]), "timeout-case")
    with pytest.raises(requests.Timeout):
        campaign.execute_plan(
            plan, tmp_path, "http://backend", client=client, checkpoint_root=tmp_path
        )
    assert client.request.call_count == 4
    journal = json.loads((tmp_path / "execution.json").read_text())
    assert journal["status"] == "interrupted"
    assert journal["cases"][0]["status"] == "submission_pending"
    assert journal["cases"][0]["graph_id"] == 1
    assert (tmp_path / "checksums.json").is_file()


def test_checkpoint_copy_rejects_escape_from_shared_root(tmp_path):
    with pytest.raises(ValueError, match="outside_root"):
        campaign._copy_checkpoints(
            {"output_filename": "/var/lib/fedsim/models/../../secret"},
            tmp_path,
            tmp_path,
            "/var/lib/fedsim/models",
        )


@pytest.mark.parametrize("defect", ["missing_peer", "wrong_mean", "nonfinite", "missing_points"])
def test_incomplete_or_invalid_server_evidence_cannot_complete_a_campaign(defect):
    case = next(
        c
        for c in campaign.build_plan(config(), "evidence-test")["cases"]
        if c["architecture"] == "spyker"
    )
    peers = {f"server-{i}": {"accuracy": 0.5, "avg_loss": 1.0} for i in range(3)}
    result = {
        "runs": [{"seed": 42}],
        "evaluation": {
            "accuracy": 0.5,
            "avg_loss": 1.0,
            "aggregation": "server_macro_mean",
            "server_count": 3,
            "per_server": peers,
        },
        "server_checkpoints": {key: "model.pth" for key in peers},
    }
    points = [{"virtual_time": 60, "server_stats": {"per_server": exchange_details()}}]
    campaign._check_result(result, case, points)
    if defect == "missing_peer":
        peers.pop("server-2")
    elif defect == "wrong_mean":
        result["evaluation"]["accuracy"] = 0.9
    elif defect == "nonfinite":
        result["evaluation"]["avg_loss"] = float("nan")
    else:
        points = []
    with pytest.raises(ValueError):
        campaign._check_result(result, case, points)


def test_wait_timeout_retains_accepted_identity_without_resubmitting(tmp_path, monkeypatch):
    def response(value):
        return SimpleNamespace(raise_for_status=lambda: None, json=lambda: value)

    client = Mock()
    client.request.side_effect = [
        response({"paths": {"/runs/{run_id}/export/evaluations": {}}}),
        response({"graph_id": 1}),
        response({}),
        response({"run_id": "accepted-job", "status": "queued"}),
        response({}),
        response({"run_id": "accepted-job", "status": "running"}),
    ]
    monkeypatch.setattr(campaign, "_check_definition", lambda *args: None)
    plan = campaign.build_plan(config(), "wait-test")
    with pytest.raises(TimeoutError, match="backend may still run"):
        campaign.execute_plan(
            plan,
            tmp_path,
            "http://backend",
            client=client,
            checkpoint_root=tmp_path,
            timeout_seconds=0,
        )
    assert client.request.call_count == 6
    entry = json.loads((tmp_path / "execution.json").read_text())["cases"][0]
    assert entry["run_id"] == "accepted-job"


def test_source_record_refuses_uncommitted_files(tmp_path):
    import subprocess

    def git(*args):
        return subprocess.check_output(["git", "-C", str(tmp_path), *args])

    git("init", "--quiet")
    (tmp_path / "uv.lock").write_text("test lock", encoding="utf-8")
    git("add", "uv.lock")
    git(
        "-c",
        "user.name=Campaign Test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "--quiet",
        "-m",
        "test fixture",
    )
    source = campaign._source_record(tmp_path)
    assert source["source_commit"] == git("rev-parse", "HEAD").decode().strip()
    (tmp_path / "untracked.txt").write_text("not archived", encoding="utf-8")
    with pytest.raises(ValueError, match="clean_committed"):
        campaign._source_record(tmp_path)


def test_old_backend_is_rejected_before_any_job_is_created(tmp_path):
    client = Mock()
    client.request.return_value = SimpleNamespace(
        raise_for_status=lambda: None, json=lambda: {"paths": {}}
    )
    with pytest.raises(ValueError, match="missing_evaluation_export"):
        campaign.execute_plan(
            campaign.build_plan(config(), "old-backend"),
            tmp_path,
            "http://backend",
            client=client,
            checkpoint_root=tmp_path,
        )
    assert client.request.call_count == 1
    journal = json.loads((tmp_path / "execution.json").read_text())
    assert journal["status"] == "interrupted" and journal["cases"] == []


def test_evaluation_export_includes_both_architectures_and_all_recorded_repetitions(
    api, monkeypatch
):
    parent = str(uuid4())
    children = [f"{parent}:hierfl:42:1", f"{parent}:spyker:42:1", f"{parent}:spyker:43:2"]
    state = {
        "results_by_architecture": {
            "hierfl": {"runs": [{"run_id": children[0]}]},
            "spyker": {"runs": [{"run_id": child} for child in children[1:]]},
        }
    }
    monkeypatch.setattr(
        simulation_run_queue.run_queue,
        "get_run_api",
        lambda run_id: state if run_id == parent else None,
    )
    for identity in [parent, *children, children[-1] + "-unrelated"]:
        assert evaluation_point_store.persist_periodic_evaluation(
            {
                "log_type": "periodic_evaluation",
                "run_id": identity,
                "architecture": "spyker" if ":spyker:" in identity else "hierarchical",
                "virtual_time": 0,
                "accuracy": 0.123456789,
                "loss": 1.23456789,
            }
        )
    response = api.get(f"/runs/{parent}/export/evaluations")
    assert response.status_code == 200
    assert {point["run_id"] for point in response.json()} == {parent, *children}
    assert all(point["accuracy"] == 0.123456789 for point in response.json())


def test_heterogeneous_network_profile_preserves_other_experiment_settings():
    baseline = config()
    network = campaign.CampaignConfig.model_validate_json(
        (CONFIG.parent / "network-sensitivity.json").read_text()
    )
    assert baseline.model_dump(exclude={"name", "network"}) == network.model_dump(
        exclude={"name", "network"}
    )
    plan = campaign.build_plan(network, "network-test")
    for case in plan["cases"]:
        clients = [n["data"]["config"] for n in case["graph"]["nodes"] if n["type"] == "ClientNode"]
        servers = [n["data"]["config"] for n in case["graph"]["nodes"] if n["type"] == "ServerNode"]
        assert [c["uploadMbps"] for c in clients] == [100, 10, 2]
        assert [c["downloadMbps"] for c in clients] == [100, 20, 5]
        assert [s["uploadMbps"] for s in servers] == [100, 25, 10]
        client_ids = {n["id"] for n in case["graph"]["nodes"] if n["type"] == "ClientNode"}
        assert [
            e["config"]["pingMs"] for e in case["graph"]["edges"] if e["source"] in client_ids
        ] == [10, 40, 100]


@pytest.mark.parametrize(
    "changes",
    [
        {"scenarios": {"-bad": [2, 2, 2]}},
        {"network": {**json.loads(CONFIG.read_text())["network"], "client_upload_mbps": [100]}},
        {"phase": "calibration"},
    ],
)
def test_invalid_networks_names_and_calibration_scope_are_rejected(changes):
    with pytest.raises(ValidationError):
        config(**changes)


def test_calibration_plan_can_be_executed_without_changing_its_bytes(tmp_path, monkeypatch):
    preview = tmp_path / "preview"
    campaign.main(["plan", "--config", str(CONFIG), "--calibrate", "--output", str(preview)])
    path = preview / "plan.json"
    preview_bytes = path.read_bytes()
    plan = campaign.read_plan(path)
    assert plan["config"]["phase"] == "calibration" and len(plan["cases"]) == 2
    source = {"source_commit": "a" * 40, "uv_lock_sha256": "b" * 64}
    environment = {
        **source,
        **{
            key: {"fixture": True}
            for key in ("runtime_versions", "hardware", "resource_budget", "dataset_provenance")
        },
    }
    environment_path = tmp_path / "environment.json"
    campaign._write_json(environment_path, environment)

    def source_record(repo):
        path.write_text("Changed in the editor after validation", encoding="utf-8")
        return source

    monkeypatch.setattr(campaign, "_source_record", source_record)
    monkeypatch.setattr(campaign.subprocess, "check_output", lambda *args: b"source ZIP fixture")
    execute = Mock()
    monkeypatch.setattr(campaign, "execute_plan", execute)
    output = tmp_path / "run"
    campaign.main(
        [
            "run",
            "--plan",
            str(path),
            "--output",
            str(output),
            "--environment",
            str(environment_path),
        ]
    )
    assert (output / "plan.json").read_bytes() == preview_bytes
    assert execute.call_args.args[0] == plan
    plan["cases"][0]["graph"]["nodes"][0]["data"]["config"]["uploadMbps"] = 999
    campaign._write_json(path, plan)
    with pytest.raises(ValueError, match="does_not_match_configuration"):
        campaign.read_plan(path)


def test_measurement_cli_requires_calibration_before_creating_output(tmp_path):
    output = tmp_path / "not-created"
    with pytest.raises(SystemExit):
        campaign.main(
            [
                "run",
                "--config",
                str(CONFIG),
                "--output",
                str(output),
                "--environment",
                "unused.json",
            ]
        )
    assert not output.exists()


def test_plan_reuse_cannot_overwrite_existing_checkpoint_directory(tmp_path):
    plan = campaign.build_plan(config(), "already-used")
    filename = plan["cases"][0]["request"]["simulation_settings"]["output_filename"]
    (tmp_path / filename).parent.mkdir(parents=True)
    client = Mock()
    client.request.return_value = SimpleNamespace(
        raise_for_status=lambda: None,
        json=lambda: {"paths": {"/runs/{run_id}/export/evaluations": {}}},
    )
    with pytest.raises(ValueError, match="directory_already_exists"):
        campaign.execute_plan(
            plan, tmp_path, "http://backend", client=client, checkpoint_root=tmp_path
        )
    assert client.request.call_count == 1


@pytest.mark.parametrize(
    "defect", ["token_only", "partial_round", "missing_counter", "boolean_counter"]
)
def test_exchange_requirement_rejects_missing_or_incomplete_peer_exchange(defect):
    case = next(
        c
        for c in campaign.build_plan(config(), "sync-proof")["cases"]
        if c["architecture"] == "spyker"
    )
    peers = {key: {"accuracy": 0.5, "avg_loss": 1.0} for key in exchange_details()}
    result = {
        "runs": [{"seed": 42}],
        "server_checkpoints": dict.fromkeys(peers, "model.pth"),
        "evaluation": {
            "accuracy": 0.5,
            "avg_loss": 1.0,
            "aggregation": "server_macro_mean",
            "server_count": 3,
            "per_server": peers,
        },
    }
    details = exchange_details()
    points = [{"virtual_time": 60, "server_stats": {"per_server": details}}]
    campaign._check_result(result, case, points)
    if defect == "token_only":
        for item in details.values():
            item["server_stats"] = dict.fromkeys(item["server_stats"], 0)
    elif defect == "partial_round":
        details["server-2"]["server_stats"]["sync_rounds_completed"] = 0
    elif defect == "missing_counter":
        details["server-0"]["server_stats"].pop("sync_rounds_initiated")
    else:
        details["server-0"]["server_stats"]["sync_rounds_initiated"] = True
    with pytest.raises(ValueError, match="missing_peer_exchange_evidence"):
        campaign._check_result(result, case, points)


def test_saved_legacy_plans_retain_default_algorithm_and_do_not_invent_sync_evidence(tmp_path):
    legacy = config(spyker_config=None, require_peer_exchange=None)
    plan = campaign.build_plan(legacy, "legacy-plan")
    assert "spyker_config" not in plan["config"]
    assert "require_peer_exchange" not in plan["config"]
    spyker = next(c for c in plan["cases"] if c["architecture"] == "spyker")
    assert spyker["request"]["spyker_config"]["h_intra"] == 350
    assert "require_peer_exchange" not in spyker
    path = tmp_path / "plan.json"
    campaign._write_json(path, plan)
    assert campaign.read_plan(path) == plan
    assert config().spyker_config.h_intra == 4


@pytest.mark.parametrize(
    "field,value",
    [("h_intra", 0), ("h_inter", True), ("decay_beta", float("nan")), ("tcp_rto_delay", -1)],
)
def test_invalid_campaign_algorithm_parameters_are_rejected(field, value):
    with pytest.raises(ValidationError):
        config(spyker_config={**config().spyker_config.model_dump(), field: value})


def test_campaign_accepts_h_inter_auto_but_not_other_strings():
    parameters = config().spyker_config.model_dump()
    assert config(spyker_config={**parameters, "h_inter": "auto"}).spyker_config.h_inter == "auto"
    with pytest.raises(ValidationError):
        config(spyker_config={**parameters, "h_inter": "fast"})


def test_status_transport_errors_are_retried_without_repeating_submissions(monkeypatch):
    monkeypatch.setattr(campaign.time, "sleep", lambda _: None)
    client = Mock()
    response = Mock()
    client.request.side_effect = [requests.ConnectionError("reset"), requests.Timeout(), response]
    assert campaign._request(client, "GET", "http://backend/runs/test") is response
    assert client.request.call_count == 3
    client.reset_mock()
    client.request.side_effect = requests.ConnectionError("reset")
    with pytest.raises(requests.ConnectionError):
        campaign._request(client, "GET", "http://backend/runs/test")
    assert client.request.call_count == 3
    for method in ("POST", "PUT"):
        client.reset_mock()
        with pytest.raises(requests.ConnectionError):
            campaign._request(client, method, "http://backend/start_simulation")
        assert client.request.call_count == 1
    client.reset_mock()
    client.request.side_effect = None
    client.request.return_value.raise_for_status.side_effect = requests.HTTPError("404")
    with pytest.raises(requests.HTTPError):
        campaign._request(client, "GET", "http://backend/runs/missing")
    assert client.request.call_count == 1


def test_runtime_sigma_is_written_to_client_nodes():
    plan = campaign.build_plan(config(client_runtime_sigma=0.02), "sigma-test")
    for case in plan["cases"]:
        clients = [n for n in case["graph"]["nodes"] if n["type"] == "ClientNode"]
        assert clients and all(n["data"]["config"]["performanceSigma"] == 0.02 for n in clients)


def test_zero_runtime_sigma_leaves_plan_unchanged():
    assert json.dumps(campaign.build_plan(config(), "sigma-test")) == json.dumps(
        campaign.build_plan(config(client_runtime_sigma=0.0), "sigma-test")
    )
    assert "client_runtime_sigma" not in campaign.build_plan(config(), "sigma-test")["config"]


def test_plan_saved_before_runtime_sigma_still_validates():
    plan = campaign.build_plan(config(), "old-plan")
    plan["config"] = old_format_config(config())
    assert "decay_mode" in plan["config"]["spyker_config"]
    assert campaign._validated_plan(plan) == plan


def test_pre_extension_archived_plan_is_accepted_without_rewriting(tmp_path):
    fixture = Path(__file__).parent / "fixtures/campaign-plan-v1.json"
    content = fixture.read_bytes()
    path = tmp_path / "plan.json"
    path.write_bytes(content)
    assert campaign.read_plan(path) == json.loads(content)
    assert path.read_bytes() == content


@pytest.mark.parametrize(
    "field,value",
    [
        ("decay_mode", "relative"),
        ("age_merge", "weighted"),
        ("aggregation_delay", True),
        ("sample_weighting", 0),
    ],
)
def test_legacy_normalization_rejects_changed_request_policy(field, value):
    plan = json.loads((Path(__file__).parent / "fixtures/campaign-plan-v1.json").read_bytes())
    plan["cases"][1]["request"]["spyker_config"][field] = value
    with pytest.raises(ValueError, match="plan_does_not_match"):
        campaign._validated_plan(plan)


def test_old_and_explicit_default_policies_compare_equally():
    plan = json.loads((Path(__file__).parent / "fixtures/campaign-plan-v1.json").read_bytes())
    explicit = campaign.build_plan(
        campaign.CampaignConfig.model_validate(plan["config"]), plan["campaign_id"]
    )
    assert campaign._comparable_plan(plan) == campaign._comparable_plan(explicit)
    assert campaign._comparable_spyker_parameters(
        plan["config"]["spyker_config"]
    ) == campaign._comparable_spyker_parameters(explicit["config"]["spyker_config"])


def test_aggregation_response_delay_is_available_to_campaigns():
    cfg = config(
        spyker_config={
            **json.loads(CONFIG.read_text())["spyker_config"],
            "aggregation_delay": True,
            "aggregation_bytes_per_second": 100_000_000,
        }
    )
    plan = campaign.build_plan(cfg, "response-delay")
    assert (
        next(case for case in plan["cases"] if case["architecture"] == "spyker")["request"][
            "spyker_config"
        ]["aggregation_delay"]
        is True
    )
