"""Reconstruct feedback decisions from verified dispatch traces, not new training."""

import argparse
import ast
import csv
import hashlib
import json
import math
import re
import statistics
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from generate_lr_ablation import Archive
from generate_population_results import expected_client_servers, require
from generate_primary_results import digest


def source_contract(archive):
    """Check the frozen rule and the single synchronous actor dispatch path."""
    source_path = archive.root / "source.zip"
    require("source.zip" in archive.manifest, "Unverified producing source")
    require(
        digest(source_path) == "0df0f5265fafe97ed9fe76ad870baca56fb6ff6d3ad58956eb810daa86156857",
        "This reconstruction has been reviewed only for the producing source snapshot",
    )
    with zipfile.ZipFile(source_path) as bundle:

        def source(suffix):
            names = [name for name in bundle.namelist() if name.endswith(suffix)]
            require(len(names) == 1, "Ambiguous source path")
            return bundle.read(names[0]).decode("utf-8")

        server = source("src/fedsim/engines/spyker/server.py")
        base = source("src/fedsim/engines/base.py")
        kernel = source("src/fedsim/simulation/orchestrator.py")
        simulation = source("src/fedsim/engines/spyker/simulation.py")
        client = source("src/fedsim/clients/actor.py")
        training = source("src/fedsim/clients/training.py")
    tree = ast.parse(server)
    actor = next(node for node in tree.body if isinstance(node, ast.ClassDef))
    require(actor.name == "SpykerServer", "Unknown actor")
    require(
        not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(tree)),
        "Async actor requires a different order analysis",
    )
    require(
        not any(isinstance(node, ast.AsyncFunctionDef) for node in ast.walk(ast.parse(base))),
        "Async base actor",
    )
    for text in [server, base, simulation]:
        require(
            not any(
                token in text
                for token in [
                    "max_concurrency",
                    "allow_out_of_order_execution",
                    "max_task_retries",
                ]
            ),
            "Nondefault ordering options require review",
        )
    method = next(
        node
        for node in actor.body
        if isinstance(node, ast.FunctionDef) and node.name == "_calculate_decay"
    )
    reference = ast.parse("""def _calculate_decay(self, client_updates, avg_updates, base_lr):
        if client_updates < avg_updates:
            return base_lr
        decayed_lr = base_lr - (self.spyker_config.decay_beta * (client_updates - avg_updates))
        return max(self.spyker_config.min_learning_rate, decayed_lr)
""").body[0]
    # The source method's docstring is irrelevant to its executable contract.
    body = (
        method.body[1:]
        if isinstance(method.body[0], ast.Expr) and isinstance(method.body[0].value, ast.Constant)
        else method.body
    )
    require(
        ast.dump(ast.Module(body=body, type_ignores=[]))
        == ast.dump(ast.Module(body=reference.body, type_ignores=[])),
        "Feedback formula changed",
    )
    require(
        "self._log_queue.put((self.global_virtual_time, payload))" in kernel,
        "Missing ordered dispatch logger",
    )
    require(
        "future = getattr(actor_ref, method_name).remote(payload, **kwargs)" in kernel,
        "Changed callback dispatch",
    )
    require(
        "num_active_clients = len(self.client_update_counts)" in server,
        "Changed active-client mean",
    )
    require(
        "avg_updates = self.total_client_updates_processed / num_active_clients" in server,
        "Changed mean denominator",
    )
    require(
        "self._schedule_client_task(client_id)" in server,
        "No one-client feedback reschedule",
    )
    require('"lr": client_lr' in server, "Rate not passed to client configuration")
    require(
        'config = data["config"]' in client
        and "self.inner_client.fit(parameters=param_arrays, config=config)" in client
        and 'lr = float(config.get("lr", 0.001))' in training
        and "train(self.net, trainloader, epochs, lr, self.device)" in training,
        "Changed rate-to-training path",
    )
    return {
        "source_zip_sha256": digest(source_path),
        "server_source_sha256": hashlib.sha256(server.encode()).hexdigest(),
        "client_source_sha256": hashlib.sha256(client.encode()).hexdigest(),
        "training_source_sha256": hashlib.sha256(training.encode()).hexdigest(),
    }


def analyze(archive):
    contract = source_contract(archive)
    membership = archive.get("cohort-membership.json")
    rows = []
    clients_out = []
    logs_out = []
    for segment in membership["segments"]:
        cases = {
            key: archive.cases[key]
            for key in segment["case_keys"]
            if archive.cases[key]["architecture"] == "spyker"
        }
        ownership = {
            node["id"]: key
            for key, case in cases.items()
            for node in case["graph"]["nodes"]
            if node["data"]["type"] == "ServerNode"
        }
        assignments = {key: expected_client_servers(case) for key, case in cases.items()}
        counts = {sid: Counter() for sid in ownership}
        rates = defaultdict(dict)
        samples = {key: {"next": [], "completed": []} for key in cases}
        client_floor = {key: Counter() for key in cases}
        log_files = defaultdict(set)
        last_times = defaultdict(float)
        seen = {}
        log_root = (archive.root / segment["runtime_log_directory"]).resolve()
        require(log_root.is_relative_to(archive.root), "Escaping log root")
        for path in sorted(log_root.rglob("worker-*.out")):
            name = path.relative_to(archive.root).as_posix()
            require(
                name in archive.manifest and digest(path) == archive.manifest[name],
                "Unverified trace",
            )
            if path.name in seen:
                require(seen[path.name] == archive.manifest[name], "Conflicting log copies")
                continue
            seen[path.name] = archive.manifest[name]
            for line in path.read_text(encoding="utf-8", errors="strict").splitlines():
                match = re.search(
                    r"\[Orchestrator\] t=([0-9.]+) \| CLIENT_UPDATE from (\S+) \(on ([^\s)]+)\)",
                    line,
                )
                if not match or match[3] not in ownership:
                    continue
                timestamp, cid, sid = match.groups()
                key = ownership[sid]
                require(assignments[key].get(cid) == sid, "Wrong client route")
                require(float(timestamp) >= last_times[key], "Nonmonotonic case trace")
                last_times[key] = float(timestamp)
                log_files[key].add(name)
                cfg = cases[key]["request"]
                eta = cfg["training_config"]["lr"]
                beta = cfg["spyker_config"]["decay_beta"]
                minimum = cfg["spyker_config"]["min_learning_rate"]
                previous = rates[sid].get(cid, eta)
                samples[key]["completed"].append(previous)
                client_floor[key][cid] += int(previous == minimum)
                counts[sid][cid] += 1
                mean = counts[sid].total() / len(counts[sid])
                rate = (
                    eta
                    if counts[sid][cid] < mean
                    else max(minimum, eta - beta * (counts[sid][cid] - mean))
                )
                require(
                    math.isfinite(rate) and minimum <= rate <= eta,
                    "Invalid reconstructed rate",
                )
                rates[sid][cid] = rate
                samples[key]["next"].append(rate)
        for key, case in cases.items():
            require(
                len(log_files[key]) == 1,
                "A case must have one complete ordered orchestrator log",
            )
            # Existing endpoint checks independently bind complete runs, four models,
            # counter totals, seeds, Loki records and checkpoint identity.
            _, _, points = archive.endpoint(key)
            work = archive.work[key]
            require(
                len(samples[key]["next"]) == work["delivered_updates"] == 14600,
                "Incomplete trace",
            )
            require(
                work["fits"] == 200 + work["delivered_updates"] == 14800,
                "Unexpected fit rescheduling",
            )
            require(set(client_floor[key]) == set(assignments[key]), "Missing clients")
            sid_list = sorted(sid for sid, owner in ownership.items() if owner == key)
            require(
                all(value == 73 for sid in sid_list for value in counts[sid].values()),
                "Unexpected client activity",
            )
            for sid in sid_list:
                require(
                    counts[sid].total()
                    == points[-1]["server_stats"]["per_server"][sid]["server_stats"][
                        "total_client_updates"
                    ],
                    "Server-local reconstructed counts differ from endpoint counters",
                )
            minimum = case["request"]["spyker_config"]["min_learning_rate"]
            row = {
                "case": key,
                "placement": case["scenario"],
                "seed": case["request"]["simulation_settings"]["seed"],
                "beta": case["request"]["spyker_config"]["decay_beta"],
                "client_updates": len(samples[key]["completed"]),
            }
            for kind in ["next", "completed"]:
                values = samples[key][kind]
                floor = sum(value == minimum for value in values)
                row.update(
                    {
                        kind + "_floor": floor,
                        kind + "_floor_pct": 100 * floor / len(values),
                        kind + "_mean_rate": statistics.mean(values),
                    }
                )
            final_floor = sum(value == minimum for sid in sid_list for value in rates[sid].values())
            require(
                row["completed_floor"] == row["next_floor"] - final_floor,
                "Completed-rate shift does not match initial and final assignments",
            )
            rows.append(row)
            for sid in sid_list:
                for cid, updates in sorted(counts[sid].items()):
                    clients_out.append(
                        {
                            "case": key,
                            "beta": row["beta"],
                            "server": sid,
                            "client": cid,
                            "completed_updates": updates,
                            "completed_at_floor": client_floor[key][cid],
                        }
                    )
            logs_out.extend(
                {"case": key, "path": name, "sha256": archive.manifest[name]}
                for name in log_files[key]
            )
    require(len(rows) == 6, "Incomplete six-case policy grid")
    return (
        rows,
        clients_out,
        {
            "archive": str(archive.root),
            "manifest_sha256": digest(archive.root / "artifact-checksums.json"),
            "source_contract": contract,
            "logs": logs_out,
        },
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    datasets = [analyze(Archive(path)) for path in [args.primary, args.feedback]]
    rows = [row for result in datasets for row in result[0]]
    require({row["beta"] for row in rows} == {0.0, 0.05}, "Unexpected intervention")
    baseline = [row for row in rows if row["beta"] == 0.05]
    require(len(baseline) == 6, "Incomplete reference cases")
    require(
        len({result[2]["source_contract"]["source_zip_sha256"] for result in datasets}) == 1,
        "Mixed producing sources",
    )
    require(
        len({(row["next_floor"], row["completed_floor"]) for row in baseline}) == 1,
        "Report per-case variation instead",
    )
    require(
        all(row["next_floor"] == row["completed_floor"] == 0 for row in rows if row["beta"] == 0),
        "Unexpected zero-penalty floor",
    )
    generated = args.paper / "generated"
    generated.mkdir(exist_ok=True, parents=True)
    for name, values in [
        ("feedback-reconstruction-values.csv", rows),
        (
            "feedback-reconstruction-clients.csv",
            [row for result in datasets for row in result[1]],
        ),
    ]:
        with (generated / name).open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)
    (generated / "feedback-reconstruction-numbers.tex").write_text(
        f"\\newcommand{{\\ReconstructedNextFloorPct}}{{{baseline[0]['next_floor_pct']:.2f}}}\n"
        f"\\newcommand{{\\ReconstructedCompletedFloorPct}}{{{baseline[0]['completed_floor_pct']:.2f}}}\n",
        encoding="utf-8",
    )
    evidence = {
        "scope": "Post-hoc deterministic control-state reconstruction under the producing source and ordered single-submitter synchronous-actor execution. Not instrumented LR telemetry, new SGD training, weight-influence attribution or a calibrated-beta intervention.",
        "ordering_reference": "https://docs.ray.io/en/latest/ray-core/actors/task-orders.html",
        "assumptions": [
            "Single synchronous server actor; default same-submitter FIFO; no failed/retried tasks in included complete cases",
            "One orchestrator log per case, preserving dispatch FIFO; rounded timestamps are not used to reorder events",
            "Client counts initialized at zero; peer messages do not change these counters",
            "Completed-update rates follow the preceding decision for the same fixed client; initial updates use the requested base rate",
            "Final next-rate decisions may schedule look-ahead work not delivered by the endpoint",
        ],
        "cases": rows,
        "inputs": [result[2] for result in datasets],
        "all_client_rows": sum(len(result[1]) for result in datasets),
    }
    (generated / "feedback-reconstruction-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    print(
        json.dumps(
            {
                "cases": len(rows),
                "next_floor_pct": baseline[0]["next_floor_pct"],
                "completed_floor_pct": baseline[0]["completed_floor_pct"],
                "new_training_runs": 0,
            }
        )
    )


if __name__ == "__main__":
    main()
