"""Generate manuscript evidence from the completed, checksum-verified population study."""

import argparse
import csv
import json
import math
import re
import statistics as stats
from collections import Counter, defaultdict
from pathlib import Path

import matplotlib
from generate_primary_results import digest, read, write_table

matplotlib.use("Agg")
from figure_style import BAND_ALPHA, HIERFL, SPYKER, finish, panels


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify_cohort_origins(manifest, verified):
    """Check derived copies against the included original segment manifests."""
    assembly = verified("COHORT-ASSEMBLY.json")
    membership = verified("cohort-membership.json")
    require(assembly["not_an_uninterrupted_execution"] is True, "Unlabelled cohort assembly")
    require(assembly["membership"] == membership, "Contradictory cohort membership")
    roots, originals = {}, {}
    for segment in assembly["segments"]:
        name = "segments/" + segment["id"] + "/original-artifact-checksums.json"
        require(
            manifest[name] == segment["original_manifest_sha256"],
            "Changed original segment manifest",
        )
        original = verified(name)
        require(
            len(original) == segment["verified_original_files"],
            "Segment inventory mismatch",
        )
        roots[segment["root"]] = segment["id"]
        originals[segment["id"]] = original
    require(
        len(roots) == len(membership["segments"]) == len(assembly["segments"]) and len(roots) >= 2,
        "Unexpected segment count",
    )
    copied = assembly["copied_files"]
    for name, origin in copied.items():
        require(manifest[name] == origin["sha256"], "Copied-file origin mismatch: " + name)
        tag = roots[origin["source_archive"]]
        if origin["source_path"] == "artifact-checksums.json":
            expected = manifest["segments/" + tag + "/original-artifact-checksums.json"]
        else:
            expected = originals[tag][origin["source_path"]]
        require(origin["sha256"] == expected, "Copy differs from original segment: " + name)
    for segment in membership["segments"]:
        require(segment["id"] in originals, "Unknown segment identity")
        for key in segment["case_keys"]:
            for prefix in ["measurements/measurement/", "evidence/measurement/"]:
                names = [name for name in manifest if name.startswith(prefix + key + "/")]
                require(bool(names), "Missing copied case: " + key)
                require(
                    all(roots[copied[name]["source_archive"]] == segment["id"] for name in names),
                    "Case assigned to the wrong segment",
                )
    return membership


def expected_client_servers(case):
    servers = {
        node["id"] for node in case["graph"]["nodes"] if node["data"]["type"] == "ServerNode"
    }
    assignments = {}
    for node in case["graph"]["nodes"]:
        if node["data"]["type"] != "ClientNode":
            continue
        neighbors = {
            edge["target"] if edge["source"] == node["id"] else edge["source"]
            for edge in case["graph"]["edges"]
            if node["id"] in [edge["source"], edge["target"]]
        } & servers
        require(len(neighbors) == 1, "Ambiguous client/server assignment")
        server = next(iter(neighbors))
        count = node["data"]["config"]["count"]
        require(type(count) is int and count > 0, "Invalid client count")
        for index in range(count):
            cid = node["id"] + (f"-{index + 1}" if count > 1 else "")
            require(cid not in assignments, "Duplicate logical client")
            assignments[cid] = server
    return assignments


def collect_work(log_root, cases):
    server_cases = {}
    counts = {case["key"]: {"fits": 0, "delivered_updates": 0} for case in cases}
    clients = {case["key"]: Counter() for case in cases}
    expected_assignments = {}
    for case in cases:
        expected_assignments[case["key"]] = expected_client_servers(case)
        for node in case["graph"]["nodes"]:
            if node["data"]["type"] == "ServerNode":
                require(
                    node["id"] not in server_cases,
                    "Server identity reused across cases",
                )
                server_cases[node["id"]] = case["key"]
    seen_files = {}
    # Ray moves older job logs into old/; include those completed jobs as well.
    for path in sorted(log_root.rglob("worker-*.out")):
        checksum = digest(path)
        if path.name in seen_files:
            require(seen_files[path.name] == checksum, "Conflicting worker-log copies")
            continue
        seen_files[path.name] = checksum
        with path.open(encoding="utf-8", errors="replace") as stream:
            for line in stream:
                if "[Orchestrator]" not in line:
                    continue
                fit = re.search(r"\| START_FIT initiated by (\S+)", line)
                update = re.search(r"\| CLIENT_UPDATE from (\S+) \(on ([^\s)]+)\)", line)
                if fit and fit[1] in server_cases:
                    counts[server_cases[fit[1]]]["fits"] += 1
                if update and update[2] in server_cases:
                    key = server_cases[update[2]]
                    require(
                        expected_assignments[key].get(update[1]) == update[2],
                        "Client update delivered to the wrong server: " + key,
                    )
                    counts[key]["delivered_updates"] += 1
                    clients[key][update[1]] += 1
    for case, values in counts.items():
        require(
            values["fits"] >= values["delivered_updates"] > 0,
            "Incomplete event trace: " + case,
        )
        require(
            clients[case].keys() == expected_assignments[case].keys(),
            "Missing/unexpected participating client: " + case,
        )
        values["unique_clients_delivered"] = len(clients[case])
        values["minimum_updates_per_client"] = min(clients[case].values())
        values["maximum_updates_per_client"] = max(clients[case].values())
        values["client_routing_verified"] = True
    return counts


def mean_sd(values, scale=1, digits=2):
    return (
        f"{scale * stats.mean(values):.{digits}f} $\\pm$ {scale * stats.stdev(values):.{digits}f}"
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    root, paper = args.archive.resolve(), args.paper.resolve()
    require(
        read(root / "completion-measurement.json")["status"] == "completed",
        "Measurements incomplete",
    )
    manifest = read(root / "artifact-checksums.json")
    for name, checksum in manifest.items():
        path = (root / name).resolve()
        require(
            path.is_relative_to(root) and digest(path) == checksum,
            "Checksum mismatch: " + name,
        )

    def verified(name):
        require(name in manifest, "Input absent from final manifest: " + name)
        return read(root / name)

    source = verified("source-record.json")
    require(
        re.fullmatch(r"[a-f0-9]{40}", source["source_commit"]),
        "Invalid source revision",
    )
    plan = verified("inputs/measurement/plan.json")
    config = plan["config"]
    require(config["seeds"] == [42, 43, 44], "Unexpected seed set")
    require(
        config["scenarios"] == {"balanced": [50] * 4, "concentrated": [140, 20, 20, 20]},
        "Unexpected placements",
    )
    require(
        config["run_time_limit"] == 60 and config["eval_interval"] == 10,
        "Unexpected endpoint",
    )
    require(len(plan["cases"]) == 12, "Incomplete measurement grid")
    require(
        verified("measurements/measurement/execution.json")["status"] == "completed",
        "Execution interrupted",
    )
    if "cohort-membership.json" in manifest:
        membership = verify_cohort_origins(manifest, verified)
        work = {}
        for segment in membership["segments"]:
            keys = segment["case_keys"]
            require(not set(keys) & work.keys(), "Case assigned to two segments")
            cases = [case for case in plan["cases"] if case["key"] in keys]
            require(len(cases) == len(keys), "Unknown segment case")
            log_root = (root / segment["runtime_log_directory"]).resolve()
            require(log_root.is_relative_to(root), "Escaping segment log path")
            work.update(collect_work(log_root, cases))
        require(
            set(work) == {case["key"] for case in plan["cases"]},
            "Incomplete cohort membership",
        )
    else:
        work = collect_work(root / "runtime/measurement/ray-logs", plan["cases"])
    groups, curves = defaultdict(list), defaultdict(list)
    records, server_records = [], []
    parents = set()
    checkpoint_count = 0
    point_count = 0
    for case in plan["cases"]:
        prefix = "measurements/measurement/" + case["key"] + "/"
        result = verified(prefix + "result.json")
        points = sorted(
            verified(prefix + "evaluations.json"),
            key=lambda point: point["virtual_time"],
        )
        copies = verified(prefix + "checkpoints.json")
        proof = verified("evidence/measurement/" + case["key"] + "/verification.json")
        settings = case["request"]["simulation_settings"]
        planned_seed = settings["seed"]
        require(
            settings["seed_set"] == [planned_seed]
            and settings["repetitions"] == 1
            and case["key"] == f"{case['scenario']}-{case['architecture']}-seed{planned_seed}",
            "Invalid planned case identity",
        )
        require(
            result["status"] == "completed"
            and result["seed"] == planned_seed
            and result["architecture"] == case["architecture"],
            "Invalid result identity",
        )
        require(result["run_id"] not in parents, "Parent run reused")
        parents.add(result["run_id"])
        require(
            [point["virtual_time"] for point in points] == list(range(0, 61, 10)),
            "Incomplete timeline",
        )
        require(len({point["run_id"] for point in points}) == 1, "Mixed child identities")
        require(
            points[0]["run_id"].startswith(result["run_id"] + ":"),
            "Child belongs to another run",
        )
        require(
            proof["automatic_loki_exact_match"] and proof["periodic_points"] == 7,
            "Missing Loki proof",
        )
        require(proof["run_id"] == points[0]["run_id"], "Loki identity mismatch")
        for filename in copies.values():
            require(prefix + filename in manifest, "Unverified checkpoint: " + filename)
        evaluation = result["evaluation"]
        accuracy, loss = evaluation["accuracy"], evaluation["avg_loss"]
        require(math.isfinite(accuracy) and 0 <= accuracy <= 1, "Invalid accuracy")
        require(math.isfinite(loss) and loss >= 0, "Invalid loss")
        row = {
            "case": case["key"],
            "placement": case["scenario"],
            "method": case["architecture"],
            "seed": result["seed"],
            "run_id": result["run_id"],
            "accuracy": accuracy,
            "loss": loss,
            "wall_seconds": result["duration_seconds"],
            "last_interval_gain_pp": 100 * (points[-1]["accuracy"] - points[-2]["accuracy"]),
            **work[case["key"]],
            "round_initiations": None,
            "peer_merges": None,
        }
        if case["architecture"] == "spyker":
            peers = evaluation["per_server"]
            require(len(peers) == 4 and len(copies) == 4, "Missing peer metrics/checkpoints")
            require(
                evaluation["aggregation"] == "server_macro_mean",
                "Unexpected evaluation scope",
            )
            require(
                math.isclose(
                    accuracy,
                    stats.mean(peer["accuracy"] for peer in peers.values()),
                    abs_tol=1e-12,
                ),
                "Incorrect macro accuracy",
            )
            require(
                math.isclose(
                    loss,
                    stats.mean(peer["avg_loss"] for peer in peers.values()),
                    abs_tol=1e-12,
                ),
                "Incorrect macro loss",
            )
            details = points[-1]["server_stats"]["per_server"]
            require(set(details) == set(peers) == set(copies), "Peer identity mismatch")
            registered_servers = [
                node for node in case["graph"]["nodes"] if node["data"]["type"] == "ServerNode"
            ]
            require(
                {node["id"] for node in registered_servers} == set(peers),
                "Unexpected peer graph mapping",
            )
            for ordinal, node in enumerate(registered_servers, 1):
                sid = node["id"]
                peer = peers[sid]
                require(
                    math.isfinite(peer["accuracy"])
                    and 0 <= peer["accuracy"] <= 1
                    and math.isfinite(peer["avg_loss"])
                    and peer["avg_loss"] >= 0,
                    "Invalid individual server metric",
                )
                server_records.append(
                    {
                        "case": case["key"],
                        "placement": case["scenario"],
                        "seed": result["seed"],
                        "server_ordinal": ordinal,
                        "server_id": sid,
                        "accuracy": peer["accuracy"],
                        "loss": peer["avg_loss"],
                        "checkpoint": copies[sid],
                        **details[sid]["server_stats"],
                    }
                )
            peer_stats = [detail["server_stats"] for detail in details.values()]
            require(
                all(detail["sync_rounds_completed"] > 0 for detail in peer_stats),
                "No completed peer exchange",
            )
            require(
                sum(detail["total_client_updates"] for detail in peer_stats)
                == row["delivered_updates"],
                "Event trace/update counter mismatch",
            )
            row["round_initiations"] = sum(detail["sync_rounds_initiated"] for detail in peer_stats)
            row["peer_merges"] = sum(detail["peer_models_aggregated"] for detail in peer_stats)
        else:
            require(len(copies) == 1, "Unexpected coordinator checkpoint count")
        for point in points:
            require(
                math.isfinite(point["accuracy"]) and math.isfinite(point["loss"]),
                "Nonfinite curve",
            )
        key = case["scenario"], case["architecture"]
        groups[key].append(row)
        curves[key].append(points)
        records.append(row)
        checkpoint_count += len(copies)
        point_count += len(points)
    require(checkpoint_count == 30 and point_count == 84, "Incomplete evidence totals")
    for rows in groups.values():
        require(
            sorted(row["seed"] for row in rows) == [42, 43, 44],
            "Missing independent run",
        )

    generated, figures = paper / "generated", paper / "figures"
    generated.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)
    table, workload = [], []
    labels = {"balanced": "50/50/50/50", "concentrated": "140/20/20/20"}
    method_labels = {"hierfl": "HierFL", "spyker": "Spyker-inspired"}
    macros = {
        "PopulationRevision": source["source_commit"][:12],
        "PopulationArtifactCount": str(len(manifest)),
    }
    cells = []
    for placement in ["balanced", "concentrated"]:
        for method in ["hierfl", "spyker"]:
            rows = groups[placement, method]
            table.append(
                [
                    labels[placement],
                    method_labels[method],
                    mean_sd([row["accuracy"] for row in rows], 100),
                    mean_sd([row["loss"] for row in rows], digits=3),
                ]
            )
            workload.append(
                [
                    labels[placement],
                    method_labels[method],
                    mean_sd([row["fits"] for row in rows], digits=0),
                    mean_sd([row["delivered_updates"] for row in rows], digits=0),
                    "--"
                    if method == "hierfl"
                    else mean_sd([row["round_initiations"] for row in rows], digits=0),
                    "--"
                    if method == "hierfl"
                    else mean_sd([row["peer_merges"] for row in rows], digits=0),
                ]
            )
            stem = (
                "Population"
                + ("Balanced" if placement == "balanced" else "Concentrated")
                + ("Hier" if method == "hierfl" else "Spy")
            )
            macros[stem] = f"{100 * stats.mean(row['accuracy'] for row in rows):.2f}"
            cells.append(
                {
                    "placement": placement,
                    "method": method,
                    "accuracy_mean": stats.mean(row["accuracy"] for row in rows),
                    "accuracy_sample_sd": stats.stdev(row["accuracy"] for row in rows),
                    "runs": rows,
                }
            )
    contrasts = []
    for method, suffix in [("hierfl", "Hier"), ("spyker", "Spy")]:
        balanced = {row["seed"]: row["accuracy"] for row in groups["balanced", method]}
        concentrated = {row["seed"]: row["accuracy"] for row in groups["concentrated", method]}
        differences = [100 * (concentrated[seed] - balanced[seed]) for seed in [42, 43, 44]]
        macros["Population" + suffix + "PlacementDelta"] = f"{stats.mean(differences):+.2f}"
        macros["Population" + suffix + "PlacementSD"] = f"{stats.stdev(differences):.2f}"
        contrasts.append(
            {
                "method": method,
                "contrast": "concentrated minus balanced",
                "paired_seeds": [42, 43, 44],
                "differences_pp": differences,
                "mean_difference_pp": stats.mean(differences),
                "sample_sd_difference_pp": stats.stdev(differences),
            }
        )
    write_table(
        generated / "population-results.tex",
        "Fixed-budget 200-client results: mean and sample SD across three seeds at 60 virtual seconds.",
        "tab:population-results",
        "llrr",
        ["Placement", "Method", "Accuracy (\\%)", "Loss"],
        table,
        wide=True,
    )
    write_table(
        generated / "population-work.tex",
        "Observed work and peer activity in the 200-client study (mean and sample SD across three seeds). Fit calls count dispatched callbacks; updates count client contributions delivered to servers. Rounds count initiations, and merges count accepted peer models.",
        "tab:population-work",
        "llrrrr",
        [
            "Placement",
            "Method",
            "Fit calls",
            "Updates",
            "Rounds",
            "Peer merges",
        ],
        workload,
        wide=True,
    )
    (generated / "population-numbers.tex").write_text(
        "\n".join("\\newcommand{\\" + key + "}{" + value + "}" for key, value in macros.items())
        + "\n",
        encoding="utf-8",
    )
    with (generated / "population-run-values.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    require(len(server_records) == 24, "Incomplete individual server inventory")
    with (generated / "population-server-values.csv").open(
        "w", newline="", encoding="utf-8"
    ) as stream:
        writer = csv.DictWriter(stream, fieldnames=list(server_records[0]))
        writer.writeheader()
        writer.writerows(server_records)
    summary = {
        "archive": str(root),
        "archive_manifest_sha256": digest(root / "artifact-checksums.json"),
        "source": source,
        "manifest_files_verified": len(manifest),
        "runs": 12,
        "periodic_points": 84,
        "checkpoints": 30,
        "cells": cells,
        "paired_placement_contrasts": contrasts,
        "individual_server_rows": 24,
        "execution_segments": verified("cohort-membership.json")
        if "cohort-membership.json" in manifest
        else None,
        "scope": "Final checkpoint endpoints; periodic snapshots are individually consistent, not globally atomic. "
        "Executed fits include terminal look-ahead work whose update can fall beyond the horizon. "
        "Delivered-update counts come from complete orchestrator logs; peer counters are checked against them.",
    }
    (generated / "population-evidence.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    figure, axes = panels()
    for axis, placement in zip(axes, ["balanced", "concentrated"], strict=True):
        for method, color in [("hierfl", HIERFL), ("spyker", SPYKER)]:
            series = curves[placement, method]
            times = [point["virtual_time"] for point in series[0]]
            values = [[100 * run[index]["accuracy"] for run in series] for index in range(7)]
            means = [stats.mean(value) for value in values]
            sd = [stats.stdev(value) for value in values]
            axis.plot(
                times,
                means,
                marker="o" if method == "hierfl" else "s",
                color=color,
                label=method_labels[method],
            )
            axis.fill_between(
                times,
                [m - s for m, s in zip(means, sd, strict=True)],
                [m + s for m, s in zip(means, sd, strict=True)],
                color=color,
                alpha=BAND_ALPHA,
                linewidth=0,
            )
    finish(
        figure,
        axes,
        ["(a) 50/50/50/50 clients", "(b) 140/20/20/20 clients"],
        60,
        figures,
        "population-learning-curves",
        accuracy_limit=40,
    )
    print(
        json.dumps(
            {
                "verified_runs": 12,
                "checkpoints": 30,
                "periodic_points": 84,
                "cells": [
                    {key: value for key, value in cell.items() if key != "runs"} for cell in cells
                ],
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
