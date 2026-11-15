"""Independent identity and arithmetic checks for the sealed repeat analysis."""

import copy
import hashlib
import importlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def analysis(monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "experiments/analysis"))
    return importlib.import_module("analyze_operational_repeats")


def envelope(definition):
    encoded = json.dumps(definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return {"definition": definition, "sha256": hashlib.sha256(encoded.encode()).hexdigest()}


def example_definition():
    return {
        "architecture": "spyker",
        "schema_version": 1,
        "runs": {
            "spyker": {
                "graph": {
                    "id": 9,
                    "nodes": [
                        {"id": "logical-A", "type": "ServerNode"},
                        {"id": "logical-B", "type": "ServerNode"},
                    ],
                    "edges": [
                        {
                            "id": 33,
                            "source_node_id": "logical-A",
                            "target_node_id": "logical-B",
                            "config": {"pingMs": 10},
                        }
                    ],
                },
                "simulation_settings": {"seed": 42},
                "training_config": {"lr": 0.01},
            }
        },
    }


def finished_state():
    return {
        "status": "completed",
        "measurement_cases": 4,
        "sealed_conditions": {"reference-beta005": 10, "control-beta0": 20},
        "phases": [
            {"condition": condition, "phase": phase, "status": "completed"}
            for condition in ("reference-beta005", "control-beta0")
            for phase in ("calibration", "measurement")
        ],
    }


def test_completed_four_phase_collection_is_accepted(analysis):
    analysis.validate_orchestration(finished_state())


@pytest.mark.parametrize(
    "problem", ["running", "missing-phase", "duplicate-phase", "failed-phase", "missing-seal"]
)
def test_incomplete_collections_are_rejected_before_analysis(analysis, problem):
    state = finished_state()
    if problem == "running":
        state["status"] = "running"
    elif problem == "missing-phase":
        state["phases"].pop()
    elif problem == "duplicate-phase":
        state["phases"][-1] = state["phases"][0]
    elif problem == "failed-phase":
        state["phases"][-1]["status"] = "failed"
    else:
        del state["sealed_conditions"]["control-beta0"]
    with pytest.raises(ValueError):
        analysis.validate_orchestration(state)


def test_only_database_graph_and_edge_ids_are_ignored(analysis):
    before = example_definition()
    after = copy.deepcopy(before)
    after["runs"]["spyker"]["graph"]["id"] = 91
    after["runs"]["spyker"]["graph"]["edges"][0]["id"] = 333
    assert analysis.scientific_definition(envelope(before)) == analysis.scientific_definition(
        envelope(after)
    )
    assert before["runs"]["spyker"]["graph"]["id"] == 9


@pytest.mark.parametrize("change", ["logical-id", "node-order", "link", "seed", "learning-rate"])
def test_scientific_identity_changes_remain_visible(analysis, change):
    before = example_definition()
    after = copy.deepcopy(before)
    run = after["runs"]["spyker"]
    if change == "logical-id":
        run["graph"]["nodes"][0]["id"] = "different-partition-identity"
    elif change == "node-order":
        run["graph"]["nodes"].reverse()
    elif change == "link":
        run["graph"]["edges"][0]["config"]["pingMs"] = 20
    elif change == "seed":
        run["simulation_settings"]["seed"] = 43
    else:
        run["training_config"]["lr"] = 0.02
    assert analysis.scientific_definition(envelope(before)) != analysis.scientific_definition(
        envelope(after)
    )


def test_tampered_captured_definition_is_rejected(analysis):
    value = envelope(example_definition())
    value["definition"]["runs"]["spyker"]["simulation_settings"]["seed"] = 43
    with pytest.raises(ValueError, match="captured definition"):
        analysis.scientific_definition(value)


def test_submitted_request_must_match_plan_except_graph_database_id(analysis):
    original = envelope(example_definition())
    case = {
        "key": "balanced-spyker-seed42",
        "architecture": "spyker",
        "request": {"training_config": {"lr": 0.01}},
    }
    request = {"graph_id": 123, **case["request"]}
    analysis.validate_case_identity(case, original, original, request)
    request["training_config"] = {"lr": 0.02}
    with pytest.raises(ValueError, match="Submitted request"):
        analysis.validate_case_identity(case, original, original, request)


def test_same_seed_factorial_contrasts_are_not_pooled(analysis):
    rows = [
        {
            "condition": "reference-beta005",
            "placement": "balanced",
            "original_accuracy": 0.1,
            "repeat_accuracy": 0.15,
        },
        {
            "condition": "reference-beta005",
            "placement": "concentrated",
            "original_accuracy": 0.2,
            "repeat_accuracy": 0.15,
        },
        {
            "condition": "control-beta0",
            "placement": "balanced",
            "original_accuracy": 0.3,
            "repeat_accuracy": 0.35,
        },
        {
            "condition": "control-beta0",
            "placement": "concentrated",
            "original_accuracy": 0.4,
            "repeat_accuracy": 0.45,
        },
    ]
    result = analysis.paired_contrasts(rows)
    assert result["placement_beta005"] == pytest.approx(
        {"original_pp": 10, "repeat_pp": 0, "repeat_minus_original_pp": -10}
    )
    assert result["feedback_balanced"] == pytest.approx(
        {"original_pp": 20, "repeat_pp": 20, "repeat_minus_original_pp": 0}
    )
    assert result["feedback_concentrated"]["repeat_pp"] == pytest.approx(30)
    assert result["feedback_by_placement_interaction"] == pytest.approx(
        {"original_pp": 0, "repeat_pp": 10, "repeat_minus_original_pp": 10}
    )


def factorial_archives():
    objects = {
        "source-record.json": {"source_commit": "source-A", "uv_lock_sha256": "lock-A"},
        "dataset-provenance.json": {"revision": "dataset-A"},
        "launch-preflight.json": {"image_id": "image-A", "cpus": 16},
        "image-inspect.json": [{"Id": "image-A"}],
        "inputs/measurement/config.json": {
            "name": "reference",
            "spyker_config": {"decay_beta": 0.05, "h_intra": 4},
            "training_config": {"learning_rate": 0.01},
            "network": {"client_latency_ms": [10, 20]},
            "seeds": [42, 43, 44],
        },
    }
    manifest = {"source.zip": "source-zip-A", "study-partitions/seed42.json": "partition-A"}
    control_objects = copy.deepcopy(objects)
    control_objects["inputs/measurement/config.json"]["name"] = "control"
    control_objects["inputs/measurement/config.json"]["spyker_config"]["decay_beta"] = 0
    reference = SimpleNamespace(get=objects.__getitem__, manifest=manifest, objects=objects)
    control = SimpleNamespace(
        get=control_objects.__getitem__, manifest=copy.deepcopy(manifest), objects=control_objects
    )
    return reference, control


def test_factorial_controls_allow_only_name_and_beta_without_mutating_inputs(analysis):
    reference, control = factorial_archives()
    before = copy.deepcopy((reference.objects, control.objects))
    analysis.validate_factorial_controls(reference, control)
    assert (reference.objects, control.objects) == before


@pytest.mark.parametrize(
    "change",
    [
        "learning-rate",
        "network",
        "list-order",
        "source",
        "source-zip",
        "image",
        "dataset",
        "partition",
        "partition-inventory",
    ],
)
def test_factorial_contrasts_reject_uncontrolled_cross_condition_changes(analysis, change):
    reference, control = factorial_archives()
    config = control.objects["inputs/measurement/config.json"]
    if change == "learning-rate":
        config["training_config"]["learning_rate"] = 0.02
    elif change == "network":
        config["network"]["client_latency_ms"][0] = 11
    elif change == "list-order":
        config["network"]["client_latency_ms"].reverse()
    elif change == "source":
        control.objects["source-record.json"]["source_commit"] = "source-B"
    elif change == "source-zip":
        control.manifest["source.zip"] = "source-zip-B"
    elif change == "image":
        control.objects["image-inspect.json"][0]["Id"] = "image-B"
    elif change == "dataset":
        control.objects["dataset-provenance.json"]["revision"] = "dataset-B"
    elif change == "partition":
        control.manifest["study-partitions/seed42.json"] = "partition-B"
    else:
        del control.manifest["study-partitions/seed42.json"]
    with pytest.raises(ValueError, match="cross-condition"):
        analysis.validate_factorial_controls(reference, control)


def test_duplicate_repeat_case_is_not_an_additional_repetition(analysis):
    with pytest.raises(ValueError, match="repeat grid"):
        analysis.paired_contrasts([{"condition": "reference-beta005", "placement": "balanced"}] * 4)


def test_initial_peer_metrics_are_checked_even_when_macro_is_equal(analysis):
    original = {
        "accuracy": 0.5,
        "loss": 1.0,
        "server_stats": {
            "per_server": {
                "a": {"accuracy": 0.4, "avg_loss": 1.0},
                "b": {"accuracy": 0.6, "avg_loss": 1.0},
            }
        },
    }
    repeat = copy.deepcopy(original)
    repeat["server_stats"]["per_server"]["a"]["accuracy"] = 0.3
    repeat["server_stats"]["per_server"]["b"]["accuracy"] = 0.7
    with pytest.raises(ValueError, match="Initial peer"):
        analysis.check_initial_metrics(original, repeat)


def loki_fixture():
    points = [
        {
            "run_id": "parent:spyker:42:1",
            "graph_id": 3,
            "virtual_time": timestamp,
            "round": timestamp,
            "accuracy": 0.1,
            "loss": 2.3,
            "server_stats": {
                "per_server": {sid: {"accuracy": 0.1, "avg_loss": 2.3} for sid in "ABCD"}
            },
        }
        for timestamp in range(0, 61, 10)
    ]
    bodies = [
        [str(index), json.dumps({"log_type": "periodic_evaluation", **point})]
        for index, point in enumerate(points)
    ]
    return points, {"status": "success", "data": {"result": [{"values": bodies}]}}


def test_loki_raw_bodies_match_all_seven_api_points(analysis):
    points, raw = loki_fixture()
    analysis.validate_loki_points(raw, points)


@pytest.mark.parametrize("problem", ["child-prefix", "missing", "duplicate", "metric"])
def test_loki_proof_is_checked_against_raw_export(analysis, problem):
    points, raw = loki_fixture()
    values = raw["data"]["result"][0]["values"]
    if problem == "child-prefix":
        record = json.loads(values[0][1])
        record["run_id"] += ":other"
        values[0][1] = json.dumps(record)
    elif problem == "missing":
        values.pop()
    elif problem == "duplicate":
        values.append(values[0])
    else:
        points[0]["accuracy"] = 0.2
    with pytest.raises(ValueError):
        analysis.validate_loki_points(raw, points)


def test_even_consistent_raw_logs_cannot_certify_nonfinite_peer_metric(analysis):
    points, raw = loki_fixture()
    points[0]["server_stats"]["per_server"]["A"]["accuracy"] = float("inf")
    raw["data"]["result"][0]["values"][0][1] = json.dumps(
        {"log_type": "periodic_evaluation", **points[0]}
    )
    with pytest.raises(ValueError, match="Nonfinite periodic peer"):
        analysis.validate_loki_points(raw, points)


ASSIGNMENTS = {"a": "A", "b": "A", "c": "B"}
ORDER_WORK = {
    "fits": 6,
    "delivered_updates": 3,
    "unique_clients_delivered": 3,
    "minimum_updates_per_client": 1,
    "maximum_updates_per_client": 1,
}


def ordered_lines(
    clients=("a", "b", "c"), prefix="[AsyncLogger | Q-Batch: 003]", timestamp="00001.000"
):
    fits = [f"{prefix} [Orchestrator] t=00000.000 | START_FIT initiated by A"] * 6
    updates = [
        f"{prefix} [Orchestrator] t={timestamp} | CLIENT_UPDATE from {client} (on {ASSIGNMENTS[client]})"
        for client in clients
    ]
    return fits + updates


def order_signature(analysis, lines, work=None):
    events, fits = analysis.extract_client_update_order(lines, ASSIGNMENTS)
    return analysis.update_order_signature(events, fits, ASSIGNMENTS, work or ORDER_WORK)


def test_client_update_order_ignores_logger_thread_and_batch_prefix(analysis):
    first = order_signature(analysis, ordered_lines())
    second = order_signature(analysis, ordered_lines(prefix="[DifferentThread | Q-Batch: 027]"))
    comparison = analysis.compare_update_orders(first, second)
    assert comparison["work_counts_equal"] and comparison["global_timestamped_order_equal"]
    assert comparison["global_identity_order_equal"]
    assert all(comparison["server_local_identity_order_equal"].values())


def test_changed_order_is_reported_without_rejecting_or_pooling_runs(analysis):
    first = order_signature(analysis, ordered_lines())
    second = order_signature(analysis, ordered_lines(clients=("c", "b", "a")))
    comparison = analysis.compare_update_orders(first, second)
    assert comparison["work_counts_equal"]
    assert not comparison["global_timestamped_order_equal"]
    assert not comparison["global_identity_order_equal"]
    assert comparison["server_local_identity_order_equal"] == {"A": False, "B": True}


def test_global_interleaving_can_change_while_server_local_order_stays_equal(analysis):
    first = order_signature(analysis, ordered_lines())
    second = order_signature(analysis, ordered_lines(clients=("a", "c", "b")))
    comparison = analysis.compare_update_orders(first, second)
    assert not comparison["global_identity_order_equal"]
    assert all(comparison["server_local_identity_order_equal"].values())


def test_timestamp_change_does_not_certify_a_client_identity_reordering(analysis):
    first = order_signature(analysis, ordered_lines())
    second = order_signature(analysis, ordered_lines(timestamp="00001.001"))
    comparison = analysis.compare_update_orders(first, second)
    assert not comparison["global_timestamped_order_equal"]
    assert comparison["global_identity_order_equal"]


@pytest.mark.parametrize("client,server", [("a", "B"), ("unknown", "A"), ("a", "unknown")])
def test_ordered_trace_rejects_misrouting(analysis, client, server):
    lines = ordered_lines()
    lines[-1] = f"[Orchestrator] t=00001.000 | CLIENT_UPDATE from {client} (on {server})"
    with pytest.raises(ValueError, match="wrong server"):
        order_signature(analysis, lines)


def test_ordered_trace_rejects_missing_client_or_count_mismatch(analysis):
    with pytest.raises(ValueError, match="participating clients"):
        order_signature(analysis, ordered_lines(clients=("a", "b")))
    with pytest.raises(ValueError, match="archived work counts"):
        order_signature(analysis, ordered_lines(clients=("a", "b", "c", "a")))


def test_different_valid_work_counts_are_reported_instead_of_filtered(analysis):
    first = order_signature(analysis, ordered_lines())
    new_work = {**ORDER_WORK, "delivered_updates": 4, "maximum_updates_per_client": 2}
    second = order_signature(analysis, ordered_lines(clients=("a", "b", "c", "a")), new_work)
    comparison = analysis.compare_update_orders(first, second)
    assert not comparison["work_counts_equal"]


def fake_order_archive(tmp_path, directory="runtime/measurement/ray-logs"):
    nodes = [{"id": sid, "data": {"type": "ServerNode"}} for sid in ("A", "B")]
    nodes += [
        {"id": cid, "data": {"type": "ClientNode", "config": {"count": 1}}} for cid in ASSIGNMENTS
    ]
    case = {
        "key": "case",
        "graph": {
            "nodes": nodes,
            "edges": [{"source": cid, "target": sid} for cid, sid in ASSIGNMENTS.items()],
        },
    }
    contents = "\n".join(ordered_lines()) + "\n"
    log = tmp_path / directory / "worker-one.out"
    log.parent.mkdir(parents=True)
    log.write_text(contents, encoding="utf-8")
    manifest = {log.relative_to(tmp_path).as_posix(): hashlib.sha256(log.read_bytes()).hexdigest()}
    return SimpleNamespace(
        root=tmp_path.resolve(), cases={"case": case}, manifest=manifest, work={"case": ORDER_WORK}
    ), log


def test_same_worker_filename_copies_require_exact_hash_and_count_once(analysis, tmp_path):
    archive, log = fake_order_archive(tmp_path)
    duplicate = log.parent / "old" / log.name
    duplicate.parent.mkdir()
    duplicate.write_bytes(log.read_bytes())
    archive.manifest[duplicate.relative_to(tmp_path).as_posix()] = hashlib.sha256(
        duplicate.read_bytes()
    ).hexdigest()
    assert analysis.case_update_order(archive, "case")["updates"] == 3
    duplicate.write_bytes(log.read_bytes() + b"different capture\n")
    archive.manifest[duplicate.relative_to(tmp_path).as_posix()] = hashlib.sha256(
        duplicate.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="Conflicting worker-log"):
        analysis.case_update_order(archive, "case")


def test_two_worker_files_cannot_be_combined_into_one_case_order(analysis, tmp_path):
    archive, log = fake_order_archive(tmp_path)
    another = log.parent / "worker-two.out"
    another.write_bytes(log.read_bytes())
    archive.manifest[another.relative_to(tmp_path).as_posix()] = hashlib.sha256(
        another.read_bytes()
    ).hexdigest()
    with pytest.raises(ValueError, match="one complete ordered"):
        analysis.case_update_order(archive, "case")


def test_order_reader_uses_only_the_retained_case_segment(analysis, tmp_path):
    directory = "runtime/measurement/retained/ray-logs"
    archive, log = fake_order_archive(tmp_path, directory)
    membership = {"segments": [{"case_keys": ["case"], "runtime_log_directory": directory}]}
    archive.manifest["cohort-membership.json"] = "membership-hash-already-verified-by-Archive"
    archive.get = {"cohort-membership.json": membership}.__getitem__
    excluded = tmp_path / "runtime/measurement/failed/ray-logs/worker-unretained.out"
    excluded.parent.mkdir(parents=True)
    excluded.write_bytes(log.read_bytes())
    # The excluded path is deliberately not in the manifest. Scanning it would fail.
    assert analysis.case_update_order(archive, "case")["updates"] == 3
