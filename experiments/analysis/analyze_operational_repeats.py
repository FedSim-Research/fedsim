"""Audit four sealed same-seed operational repeats separately from the primary cohort."""

import argparse
import copy
import csv
import hashlib
import json
import math
import re
import zipfile
from collections import Counter
from pathlib import Path

from generate_lr_ablation import Archive
from generate_population_results import expected_client_servers, require
from generate_primary_results import digest, read, write_table

CONDITIONS = {"reference-beta005": 0.05, "control-beta0": 0.0}
CASE_KEYS = ("balanced-spyker-seed42", "concentrated-spyker-seed42")
CLIENT_UPDATE = re.compile(
    r"\[Orchestrator\] t=([0-9.]+) \| CLIENT_UPDATE from (\S+) \(on ([^\s)]+)\)"
)


def extract_client_update_order(lines, assignments):
    """Keep printed dispatch order while ignoring logger thread/batch prefixes."""
    servers, events, fits = set(assignments.values()), [], 0
    previous_time = -1.0
    for line in lines:
        if "[Orchestrator]" not in line:
            continue
        fit = re.search(r"\| START_FIT initiated by (\S+)", line)
        if fit and fit[1] in servers:
            fits += 1
        update = CLIENT_UPDATE.search(line)
        if update is None:
            continue
        timestamp, client, server = update.groups()
        if client not in assignments and server not in servers:
            continue
        require(assignments.get(client) == server, "Client update delivered to the wrong server")
        current_time = float(timestamp)
        require(
            math.isfinite(current_time) and current_time >= previous_time,
            "Nonmonotonic logged client-update time",
        )
        previous_time = current_time
        events.append((timestamp, client, server))
    return events, fits


def update_order_signature(events, fits, assignments, expected_work):
    """Require complete own-case counts; fingerprint order without comparing outcomes."""
    clients = Counter(client for _timestamp, client, _server in events)
    require(
        bool(clients) and clients.keys() == assignments.keys(), "Incomplete participating clients"
    )
    require(
        all(assignments[client] == server for _timestamp, client, server in events),
        "Client update delivered to the wrong server",
    )
    work = {
        "fits": fits,
        "delivered_updates": len(events),
        "unique_clients_delivered": len(clients),
        "minimum_updates_per_client": min(clients.values()),
        "maximum_updates_per_client": max(clients.values()),
    }
    require(
        fits >= len(events) > 0 and all(expected_work[key] == value for key, value in work.items()),
        "Incomplete ordered trace or disagreement with archived work counts",
    )

    def fingerprint(values):
        return hashlib.sha256(
            json.dumps(values, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()
        ).hexdigest()

    def signatures(values):
        return {
            "updates": len(values),
            "timestamped_order_sha256": fingerprint(values),
            "identity_order_sha256": fingerprint(
                [(client, server) for _, client, server in values]
            ),
        }

    return {
        "work": work,
        **signatures(events),
        "per_server": {
            server: signatures([event for event in events if event[2] == server])
            for server in sorted(set(assignments.values()))
        },
    }


def case_update_order(archive, key):
    """Use exactly one manifest-bound orchestrator log from this case's retained segment."""
    directory = "runtime/measurement/ray-logs"
    if "cohort-membership.json" in archive.manifest:
        matches = [
            segment
            for segment in archive.get("cohort-membership.json")["segments"]
            if key in segment["case_keys"]
        ]
        require(len(matches) == 1, "Ambiguous retained case segment")
        directory = matches[0]["runtime_log_directory"]
    log_root = (archive.root / directory).resolve()
    require(log_root.is_relative_to(archive.root), "Escaping ordered log root")
    assignments = expected_client_servers(archive.cases[key])
    seen, candidates = {}, []
    for path in sorted(log_root.rglob("worker-*.out")):
        name = path.relative_to(archive.root).as_posix()
        require(name in archive.manifest, "Unmanifested ordered log")
        checksum = digest(path)
        require(checksum == archive.manifest[name], "Changed ordered log")
        if path.name in seen:
            require(seen[path.name] == checksum, "Conflicting worker-log copies")
            continue
        seen[path.name] = checksum
        events, fits = extract_client_update_order(
            path.read_text(encoding="utf-8", errors="strict").splitlines(), assignments
        )
        if events or fits:
            candidates.append((name, checksum, events, fits))
    require(len(candidates) == 1, "A case must have one complete ordered orchestrator log")
    name, checksum, events, fits = candidates[0]
    return {
        "source_log": name,
        "source_log_sha256": checksum,
        **update_order_signature(events, fits, assignments, archive.work[key]),
    }


def compare_update_orders(original, repeat):
    require(
        set(original["per_server"]) == set(repeat["per_server"]), "Changed server order mapping"
    )
    return {
        "work_counts_equal": original["work"] == repeat["work"],
        "global_timestamped_order_equal": original["timestamped_order_sha256"]
        == repeat["timestamped_order_sha256"],
        "global_identity_order_equal": original["identity_order_sha256"]
        == repeat["identity_order_sha256"],
        "server_local_timestamped_order_equal": {
            sid: original["per_server"][sid]["timestamped_order_sha256"]
            == repeat["per_server"][sid]["timestamped_order_sha256"]
            for sid in original["per_server"]
        },
        "server_local_identity_order_equal": {
            sid: original["per_server"][sid]["identity_order_sha256"]
            == repeat["per_server"][sid]["identity_order_sha256"]
            for sid in original["per_server"]
        },
    }


def validate_orchestration(state):
    """Reject unfinished collections before opening any condition result files."""
    require(state.get("status") == "completed", "Operational repeats are not completed")
    require(state.get("measurement_cases") == 4, "Expected exactly four measurement cases")
    require(set(state.get("sealed_conditions", {})) == set(CONDITIONS), "Unsealed conditions")
    expected = {
        (condition, phase) for condition in CONDITIONS for phase in ("calibration", "measurement")
    }
    actual = [(row.get("condition"), row.get("phase")) for row in state.get("phases", [])]
    require(len(actual) == len(expected) and set(actual) == expected, "Incomplete phase grid")
    require(all(row.get("status") == "completed" for row in state["phases"]), "Incomplete phase")


def scientific_definition(envelope):
    """Keep logical identities and ordering; remove only database-generated IDs."""
    definition = envelope["definition"]
    encoded = json.dumps(
        definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    require(
        hashlib.sha256(encoded.encode()).hexdigest() == envelope["sha256"],
        "Changed captured definition",
    )
    require(
        definition["architecture"] == "spyker" and set(definition["runs"]) == {"spyker"},
        "Unexpected architecture",
    )
    result = copy.deepcopy(definition)
    graph = result["runs"]["spyker"]["graph"]
    graph.pop("id")
    for edge in graph["edges"]:
        edge.pop("id")
    return result


def validate_case_identity(planned_case, original_definition, repeat_definition, repeat_request):
    require(
        planned_case["key"] in CASE_KEYS and planned_case["architecture"] == "spyker",
        "Unexpected selected case",
    )
    request = copy.deepcopy(repeat_request)
    request.pop("graph_id")
    require(request == planned_case["request"], "Submitted request differs from frozen plan")
    before = scientific_definition(original_definition)
    after = scientific_definition(repeat_definition)
    require(before == after, "Changed logical topology or scientific settings")
    require(after["runs"]["spyker"]["simulation_settings"]["seed"] == 42, "Unexpected repeat seed")
    return {
        "original_definition_sha256": original_definition["sha256"],
        "repeat_definition_sha256": repeat_definition["sha256"],
    }


def check_initial_metrics(original, repeat):
    for key in ("accuracy", "loss"):
        require(
            math.isclose(original[key], repeat[key], rel_tol=0, abs_tol=1e-12),
            "Initial metrics differ",
        )
    left, right = original["server_stats"]["per_server"], repeat["server_stats"]["per_server"]
    require(set(left) == set(right), "Initial server identities differ")
    for sid in left:
        for metric in ("accuracy", "avg_loss"):
            require(
                math.isclose(left[sid][metric], right[sid][metric], rel_tol=0, abs_tol=1e-12),
                "Initial peer metrics differ",
            )


def validate_loki_points(raw, points):
    """Cross-check the archived Loki bodies, not just a recorded success flag."""
    require(raw["status"] == "success", "Unsuccessful Loki export")
    require(len(points) == 7, "Incomplete periodic evaluation grid")
    child = points[0]["run_id"]
    by_time = {}
    for stream in raw["data"]["result"]:
        for _timestamp, body in stream["values"]:
            event = json.loads(body)
            require(event.get("log_type") == "periodic_evaluation", "Unexpected Loki event type")
            require(event.get("run_id") == child, "Loki child-run identity differs")
            timestamp = event["virtual_time"]
            require(timestamp not in by_time, "Duplicate Loki evaluation time")
            by_time[timestamp] = event
    require(
        set(by_time) == {point["virtual_time"] for point in points}, "Loki evaluation times differ"
    )
    for point in points:
        require(point["run_id"] == child, "Mixed API child-run identities")
        require(
            all(
                by_time[point["virtual_time"]][key] == point[key]
                for key in ("run_id", "graph_id", "round", "accuracy", "loss", "server_stats")
            ),
            "Loki and API evaluation bodies differ",
        )
        require(
            math.isfinite(point["accuracy"])
            and 0 <= point["accuracy"] <= 1
            and math.isfinite(point["loss"]),
            "Nonfinite periodic metric",
        )
        peers = point["server_stats"]["per_server"]
        require(len(peers) == 4, "Incomplete periodic server evaluation")
        require(
            all(
                math.isfinite(peer[metric])
                for peer in peers.values()
                for metric in ("accuracy", "avg_loss")
            ),
            "Nonfinite periodic peer metric",
        )


def paired_contrasts(rows):
    """Describe original/repeated factorial contrasts, never pooling observations."""
    grid = {(row["condition"], row["placement"]): row for row in rows}
    require(len(rows) == 4 and len(grid) == 4, "Incomplete or duplicate repeat grid")
    require(
        set(grid)
        == {
            (condition, placement)
            for condition in CONDITIONS
            for placement in ("balanced", "concentrated")
        },
        "Unexpected repeat grid",
    )

    def contrasts(field):
        ref_bal = grid["reference-beta005", "balanced"][field]
        ref_con = grid["reference-beta005", "concentrated"][field]
        ctl_bal = grid["control-beta0", "balanced"][field]
        ctl_con = grid["control-beta0", "concentrated"][field]
        require(
            all(
                math.isfinite(value) and 0 <= value <= 1
                for value in (ref_bal, ref_con, ctl_bal, ctl_con)
            ),
            "Invalid endpoint accuracy",
        )
        return {
            "placement_beta005": 100 * (ref_con - ref_bal),
            "placement_beta0": 100 * (ctl_con - ctl_bal),
            "feedback_balanced": 100 * (ctl_bal - ref_bal),
            "feedback_concentrated": 100 * (ctl_con - ref_con),
            "feedback_by_placement_interaction": 100 * ((ctl_con - ref_con) - (ctl_bal - ref_bal)),
        }

    original, repeat = contrasts("original_accuracy"), contrasts("repeat_accuracy")
    return {
        key: {
            "original_pp": original[key],
            "repeat_pp": repeat[key],
            "repeat_minus_original_pp": repeat[key] - original[key],
        }
        for key in original
    }


def validate_factorial_controls(reference, control):
    """Only beta may differ between the two original conditions of this repeat grid."""
    for name in ("source-record.json", "dataset-provenance.json", "launch-preflight.json"):
        require(
            reference.get(name) == control.get(name), "Different cross-condition input: " + name
        )
    require(
        reference.manifest.get("source.zip")
        and reference.manifest["source.zip"] == control.manifest.get("source.zip"),
        "Different cross-condition producing source ZIP",
    )
    require(
        reference.get("image-inspect.json")[0]["Id"] == control.get("image-inspect.json")[0]["Id"],
        "Different cross-condition producing image",
    )
    partitions = {name for name in reference.manifest if name.startswith("study-partitions/")}
    require(
        partitions
        and partitions
        == {name for name in control.manifest if name.startswith("study-partitions/")},
        "Different cross-condition partition inventory",
    )
    for name in sorted(partitions):
        require(
            reference.manifest[name] == control.manifest[name],
            "Different cross-condition planned partition: " + name,
        )
    before = copy.deepcopy(reference.get("inputs/measurement/config.json"))
    after = copy.deepcopy(control.get("inputs/measurement/config.json"))
    before.pop("name")
    after.pop("name")
    require(
        before["spyker_config"]["decay_beta"] == CONDITIONS["reference-beta005"]
        and after["spyker_config"]["decay_beta"] == CONDITIONS["control-beta0"],
        "Unexpected cross-condition feedback coefficients",
    )
    before["spyker_config"]["decay_beta"] = CONDITIONS["control-beta0"]
    require(before == after, "Uncontrolled cross-condition configuration difference")


def verify_parent_inputs(repeat, original):
    """Bind copied inputs to both the retained cohort and its original segment."""
    parent = repeat.get("parent-record.json")
    require(parent["selected_cases"] == list(CASE_KEYS), "Changed prespecified selected cases")
    segment = next(
        (
            row
            for row in original.get("COHORT-ASSEMBLY.json")["segments"]
            if row["root"].replace("\\", "/").rsplit("/", 1)[-1] == parent["parent_archive"]
        ),
        None,
    )
    require(segment is not None, "Parent segment is absent from retained cohort")
    manifest_name = f"segments/{segment['id']}/original-artifact-checksums.json"
    require(
        original.manifest[manifest_name]
        == parent["parent_manifest_sha256"]
        == segment["original_manifest_sha256"],
        "Changed parent segment manifest",
    )
    original_manifest = original.get(manifest_name)
    for name, expected in parent["parent_inputs_unchanged"].items():
        require(
            name in original_manifest and original_manifest[name] == expected,
            "Parent input is not source-bound: " + name,
        )
        require(
            repeat.manifest.get(name) == original.manifest.get(name) == expected,
            "Repeat changed input: " + name,
        )
    require(
        set(parent["parent_inputs_unchanged"])
        == {
            f"inputs/{phase}/{name}"
            for phase in ("calibration", "measurement")
            for name in ("config.json", "plan.json")
        },
        "Incomplete parent input map",
    )
    for name in ("source.zip", "source-record.json", "dataset-provenance.json"):
        require(
            repeat.manifest[name] == original.manifest[name], "Different producing input: " + name
        )
    require(
        parent["source_zip_sha256"] == repeat.manifest["source.zip"], "Parent source ZIP mismatch"
    )
    partition_names = {name for name in original.manifest if name.startswith("study-partitions/")}
    require(
        partition_names
        and partition_names
        == {name for name in repeat.manifest if name.startswith("study-partitions/")},
        "Different partition inventory",
    )
    require(
        all(repeat.manifest[name] == original.manifest[name] for name in partition_names),
        "Different planned partitions",
    )
    with zipfile.ZipFile(repeat.root / "source.zip") as source:
        lock_names = [
            name for name in source.namelist() if name == "uv.lock" or name.endswith("/uv.lock")
        ]
        require(len(lock_names) == 1, "Ambiguous producing lock")
        require(
            hashlib.sha256(source.read(lock_names[0])).hexdigest()
            == repeat.get("source-record.json")["uv_lock_sha256"],
            "Producing lock declaration mismatch",
        )
    selection = repeat.get("inputs/measurement/selection.json")
    require(
        selection["selected_case_keys"] == list(CASE_KEYS), "Changed operational repeat selection"
    )
    require(
        selection["parent_plan_sha256"] == repeat.manifest["inputs/measurement/plan.json"],
        "Selection does not bind its parent plan",
    )


def validate_finished_condition(archive):
    source = archive.get("source-record.json")
    for phase in ("calibration", "measurement"):
        completion = archive.get(f"completion-{phase}.json")
        require(
            completion["status"] == "completed"
            and completion["cases"] == 2
            and completion["source"] == source,
            "Incomplete phase or mismatched producing source",
        )
        container = archive.get(f"container-final-{phase}.json")
        require(
            not container["Running"] and not container["OOMKilled"] and container["ExitCode"] == 0,
            "Container did not finish cleanly",
        )
    image = archive.get("image-inspect.json")[0]["Id"]
    require(
        archive.get("launch-preflight.json")["image_id"] == image,
        "Launch image declaration mismatch",
    )
    for name in (
        "concurrent-containers-measurement.jsonl",
        "resources-measurement.jsonl",
        "host-memory-measurement.jsonl",
    ):
        require(name in archive.manifest, "Missing operational resource record: " + name)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repeat-root", type=Path, required=True)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    root = args.repeat_root.resolve()
    state = read(root / "orchestration-status.json")
    validate_orchestration(state)
    comparison = read(root / "repeat-comparison.json")
    records = {(row["condition"], row["case"]): row for row in comparison["cases"]}
    require(len(comparison["cases"]) == len(records) == 4, "Incomplete orchestration comparison")
    require(
        set(records) == {(condition, key) for condition in CONDITIONS for key in CASE_KEYS},
        "Unexpected summary cases",
    )
    originals = {
        "reference-beta005": Archive(args.primary),
        "control-beta0": Archive(args.feedback),
    }
    validate_factorial_controls(originals["reference-beta005"], originals["control-beta0"])
    rows, bindings = [], []
    for condition, beta in CONDITIONS.items():
        repeat, original = Archive(root / condition), originals[condition]
        require(
            state["sealed_conditions"][condition] == len(repeat.manifest),
            "Sealed-condition inventory differs",
        )
        validate_finished_condition(repeat)
        verify_parent_inputs(repeat, original)
        require(
            repeat.get("image-inspect.json")[0]["Id"]
            == original.get("image-inspect.json")[0]["Id"],
            "Different producing image",
        )
        for key in CASE_KEYS:
            require(repeat.cases[key] == original.cases[key], "Changed frozen planned case")
            require(
                repeat.cases[key]["request"]["spyker_config"]["decay_beta"] == beta,
                "Unexpected condition penalty",
            )
            prefix = f"measurements/measurement/{key}/"
            binding = validate_case_identity(
                repeat.cases[key],
                original.get(prefix + "definition.json"),
                repeat.get(prefix + "definition.json"),
                repeat.get(prefix + "request.json"),
            )
            left, _, old_points = original.endpoint(key)
            right, _, points = repeat.endpoint(key)
            for archive, timeline in ((original, old_points), (repeat, points)):
                evidence_prefix = f"evidence/measurement/{key}/"
                validate_loki_points(archive.get(evidence_prefix + "loki-raw.json"), timeline)
                case_checksums = archive.get(evidence_prefix + "case-checksums.json")
                require(
                    bool(case_checksums)
                    and all(
                        archive.manifest.get(prefix + name) == checksum
                        for name, checksum in case_checksums.items()
                    ),
                    "Case checksum manifest disagrees with whole archive",
                )
            require(
                right["run_id"] != left["run_id"],
                "Operational repeat reuses its original run identity",
            )
            require(
                right["seed"] == left["seed"] == 42
                and right["current_sim_time"] == right["run_time_limit"] == 60,
                "Different repeat seed or horizon",
            )
            check_initial_metrics(old_points[0], points[0])
            original_order = case_update_order(original, key)
            repeat_order = case_update_order(repeat, key)
            order_comparison = compare_update_orders(original_order, repeat_order)
            old_accuracy, new_accuracy = (
                left["evaluation"]["accuracy"],
                right["evaluation"]["accuracy"],
            )
            delta = 100 * (new_accuracy - old_accuracy)
            summary = records[condition, key]
            require(
                summary["seed"] == 42 and summary["repeat_run_id"] == right["run_id"],
                "Summary identity mismatch",
            )
            require(
                summary["original_evaluation"] == left["evaluation"]
                and summary["repeat_evaluation"] == right["evaluation"],
                "Summary metrics differ from archived results",
            )
            for field, expected in (
                ("original_accuracy", old_accuracy),
                ("repeat_accuracy", new_accuracy),
                ("accuracy_delta_pp", delta),
            ):
                require(
                    math.isclose(summary[field], expected, rel_tol=0, abs_tol=1e-12),
                    "Summary endpoint differs: " + field,
                )
            duration = right["duration_seconds"]
            require(
                math.isfinite(duration)
                and duration > 0
                and summary["repeat_wall_seconds"] == duration,
                "Invalid case duration record",
            )
            rows.append(
                {
                    "condition": condition,
                    "beta": beta,
                    "case": key,
                    "placement": repeat.cases[key]["scenario"],
                    "seed": 42,
                    "original_run_id": left["run_id"],
                    "repeat_run_id": right["run_id"],
                    "original_accuracy": old_accuracy,
                    "repeat_accuracy": new_accuracy,
                    "accuracy_delta_pp": delta,
                    "original_loss": left["evaluation"]["avg_loss"],
                    "repeat_loss": right["evaluation"]["avg_loss"],
                    "repeat_case_wall_seconds": duration,
                    **{
                        f"{side}_{counter}": value
                        for side, sequence in (
                            ("original", original_order),
                            ("repeat", repeat_order),
                        )
                        for counter, value in sequence["work"].items()
                    },
                    "work_counts_equal": order_comparison["work_counts_equal"],
                    "original_timestamped_order_sha256": original_order["timestamped_order_sha256"],
                    "repeat_timestamped_order_sha256": repeat_order["timestamped_order_sha256"],
                    "global_timestamped_order_equal": order_comparison[
                        "global_timestamped_order_equal"
                    ],
                    "original_identity_order_sha256": original_order["identity_order_sha256"],
                    "repeat_identity_order_sha256": repeat_order["identity_order_sha256"],
                    "global_identity_order_equal": order_comparison["global_identity_order_equal"],
                    "all_server_local_timestamped_orders_equal": all(
                        order_comparison["server_local_timestamped_order_equal"].values()
                    ),
                    "all_server_local_identity_orders_equal": all(
                        order_comparison["server_local_identity_order_equal"].values()
                    ),
                }
            )
            bindings.append(
                {
                    "condition": condition,
                    "case": key,
                    **binding,
                    "logged_client_update_order": {
                        "original": original_order,
                        "repeat": repeat_order,
                        "comparison": order_comparison,
                    },
                }
            )
        bindings.append(
            {
                "condition": condition,
                "original_archive": str(original.root),
                "original_manifest_sha256": digest(original.root / "artifact-checksums.json"),
                "repeat_archive": str(repeat.root),
                "repeat_manifest_sha256": digest(repeat.root / "artifact-checksums.json"),
                "repeat_files_verified": len(repeat.manifest),
                "source": repeat.get("source-record.json"),
            }
        )
    contrasts = paired_contrasts(rows)
    generated = args.paper / "generated"
    generated.mkdir(parents=True, exist_ok=True)
    with (generated / "operational-repeat-grid.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    write_table(
        generated / "operational-repeat-grid.tex",
        "Same-seed operational repeats at 200 clients. Accuracy (\\%) and repeat-minus-original differences (pp) use the server macro mean. All four repeat cases use seed 42; they remain separate from the original 42-run cohort.",
        "tab:operational-repeat-grid",
        "rcrrr",
        [r"$\beta$", "Placement", "Original", "Repeat", r"$\Delta$ (pp)"],
        [
            [
                f"{row['beta']:.2f}",
                "Bal." if row["placement"] == "balanced" else "Conc.",
                f"{100 * row['original_accuracy']:.2f}",
                f"{100 * row['repeat_accuracy']:.2f}",
                f"{row['accuracy_delta_pp']:+.2f}",
            ]
            for row in rows
        ],
    )
    evidence = {
        "scope": "Four prespecified physical operational repeats of archived seed 42 cases; no added independent training seeds, pooling with the original 42 learning runs, significance or throughput claim.",
        "primary_metric": "server_macro_mean",
        "contrasts_pp": contrasts,
        "cases": rows,
        "bindings": bindings,
        "orchestration_status_sha256": digest(root / "orchestration-status.json"),
        "orchestration_comparison_sha256": digest(root / "repeat-comparison.json"),
        "resource_scope": "Per-case wall durations and concurrent-container/resource records are preserved for provenance. The observations do not isolate physical throughput or attribute variation to a specific scheduler or worker mechanism.",
        "ordering_scope": "Canonical sequence digests retain only the filtered CLIENT_UPDATE tuples (printed virtual-time string, client ID, server ID), globally and per server. Identity-only digests additionally distinguish changed client ordering from changed rounded timestamps. Logger prefixes and batch sizes are excluded. Work and order differences are reported, never filtered out. These dispatcher-log comparisons do not reconstruct model payloads or establish a cause of accuracy differences; identical logged client order does not certify identical whole-runtime execution.",
    }
    (generated / "operational-repeat-grid-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cases": len(rows),
                "seed": 42,
                "new_independent_seeds": 0,
                "maximum_absolute_endpoint_delta_pp": max(
                    abs(row["accuracy_delta_pp"]) for row in rows
                ),
            }
        )
    )


if __name__ == "__main__":
    main()
