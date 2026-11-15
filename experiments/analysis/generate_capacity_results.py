"""Report short capacity probes separately from learning-quality experiments."""

import argparse
import csv
import json
import re
from pathlib import Path

from generate_population_results import expected_client_servers
from generate_primary_results import digest, read, write_table

REVISION = "20d507096582de5b5055cb80127c14b15f3cf387"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verified_archive(root):
    root = root.resolve()
    manifest = read(root / "artifact-checksums.json")
    for name, expected in manifest.items():
        path = (root / name).resolve()
        require(path.is_relative_to(root), "Escaping archive path")
        require(digest(path) == expected, "Checksum mismatch: " + name)

    def get(name):
        require(name in manifest, "Unverified capacity input: " + name)
        return read(root / name)

    return manifest, get


def census(root, case):
    servers = {
        node["id"] for node in case["graph"]["nodes"] if node["data"]["type"] == "ServerNode"
    }
    unique, fits, deliveries = set(), 0, 0
    assignments = expected_client_servers(case)
    for path in (root / "logs/ray-workers").rglob("worker-*.out"):
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
            if "[Orchestrator]" not in line:
                continue
            fit = re.search(r"\| START_FIT initiated by (\S+)", line)
            update = re.search(r"\| CLIENT_UPDATE from (\S+) \(on ([^\s)]+)\)", line)
            if fit and fit[1] in servers:
                fits += 1
            if update and update[2] in servers:
                require(
                    assignments.get(update[1]) == update[2],
                    "Client update delivered to the wrong server",
                )
                deliveries += 1
                unique.add(update[1])
    return len(unique), fits, deliveries


def worker_census(root):
    """Count actual training actors independently of legacy client counters."""
    names = set()
    for path in (root / "logs/ray-workers").rglob("worker-*.out"):
        with path.open(encoding="utf-8", errors="replace") as stream:
            initial = stream.read(1024)
        if ":actor_name:CpuExecutionWorker" in initial:
            names.add(path.name)
    return len(names)


def row(root, method, workers, get):
    prefix = method + "/"
    status = get(prefix + "status.json")
    result = get(prefix + "result.json")
    case = get(prefix + "case.json")
    audit = get(prefix + "case-final-audit.json")
    state = get(prefix + "container-final-state.json")
    require(status["architecture"] == method, "Method mismatch")
    require(case["architecture"] == method, "Plan method mismatch")
    require(
        type(status["clients"]) is int and status["clients"] == len(expected_client_servers(case)),
        "Requested client count differs from the captured topology",
    )
    require(status["oom_kills_observed"] == 0, "Unexpected OOM")
    require(not state["Running"] and not state["OOMKilled"], "Live/OOM container")
    require(
        audit["actual_container_resources"]["NanoCpus"] == workers * 10**9,
        "Worker budget mismatch",
    )
    unique, fits, updates = census(root / method, case)
    observed_workers = worker_census(root / method)
    require(observed_workers == workers, "Training actor census differs from worker budget")
    complete = status["status"] == "completed"
    if complete:
        require(state["ExitCode"] == 0, "Unsuccessful completed container")
        require(result["status"] == "completed", "Incomplete backend result")
        require(result["current_sim_time"] == 2, "Different functional horizon")
        require(unique == status["clients"], "Not every requested client contributed")
    else:
        reason = status.get("reason")
        require(
            status["status"] == "aborted"
            and reason in ["host_memory_guard", "memory_guard", "wall_time_limit"],
            "Unexpected failure class",
        )
        limits = get("limits.json")
        if reason == "host_memory_guard":
            require(bool(get(prefix + "abort-request.json")), "Missing host-guard evidence")
        elif reason == "memory_guard":
            require(
                status["memory_bytes"] >= limits["soft_abort_memory_bytes"],
                "Missing cgroup-guard evidence",
            )
        else:
            from datetime import datetime

            elapsed = (
                datetime.fromisoformat(status["aborted_at"])
                - datetime.fromisoformat(status["accepted_at"])
            ).total_seconds()
            require(
                elapsed >= limits["wall_limit_seconds_per_architecture"],
                "Missing wall-limit evidence",
            )
    return {
        "archive": str(root),
        "method": method,
        "clients_requested": status["clients"],
        "cpu_workers": workers,
        "training_worker_actor_logs": observed_workers,
        "object_store_gib": audit["object_store_bytes_from_archived_ray_command"] / 2**30,
        "shm_gib": audit["actual_container_resources"]["ShmSize"] / 2**30,
        "status": "completed"
        if complete
        else {
            "host_memory_guard": "host guard",
            "memory_guard": "cgroup guard",
            "wall_time_limit": "wall-time limit",
        }[status["reason"]],
        "controlled_stop_reason": None if complete else status["reason"],
        "virtual_horizon": 2,
        "unique_clients_delivered": unique,
        "fit_dispatches": fits,
        "delivered_updates": updates,
        "peak_cgroup_gib": status["peak_memory_bytes"] / 2**30,
        "oom_kills": 0,
        "scope": "Functional capacity only; no isolated wall-clock or convergence claim",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--four-workers", type=Path)
    parser.add_argument("--additional-four-workers", type=Path, action="append", default=[])
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    records, archives = [], []
    for count in [500, 1000]:
        root = args.candidate / f"n{count}"
        manifest, get = verified_archive(root)
        resolution = get("candidate-runtime-resolution.json")
        require(resolution["resolved_runtime_commit"] == REVISION, "Different runtime")
        require(
            resolution["direct_original_image_installed_package_check"]["installed_package_equal"]
            and resolution["direct_original_image_installed_package_check"]["uv_lock_equal"],
            "Unresolved candidate runtime",
        )
        archives.append({"archive": str(root), "verified_files": len(manifest)})
        for method in ["hierfl", "spyker"]:
            records.append(row(root, method, 8, get))
    four_worker_roots = (
        [args.four_workers] if args.four_workers else []
    ) + args.additional_four_workers
    for root in four_worker_roots:
        manifest, get = verified_archive(root)
        require(get("source-record.json")["source_commit"] == REVISION, "Different runtime")
        archives.append({"archive": str(root), "verified_files": len(manifest)})
        method = "hierfl" if root.name == "n2000" else "spyker"
        records.append(row(root, method, 4, get))
    generated = args.paper / "generated"
    generated.mkdir(exist_ok=True)
    write_table(
        generated / "capacity-results.tex",
        "Short functional capacity probes at a two-second virtual horizon. RAM is peak cgroup usage, including cache and object storage; all probes use a 22-GiB cgroup limit. A completed probe requires an update from every requested client.",
        "tab:capacity",
        "lrrrlr",
        ["Method", "Clients", "Workers", "Store (GiB)", "Outcome", "RAM (GiB)"],
        [
            [
                "HierFL" if record["method"] == "hierfl" else "Spyker-inspired",
                str(record["clients_requested"]),
                str(record["cpu_workers"]),
                f"{record['object_store_gib']:.0f}",
                record["status"],
                f"{record['peak_cgroup_gib']:.2f}",
            ]
            for record in records
        ],
        wide=True,
    )
    with (generated / "capacity-values.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    (generated / "capacity-evidence.json").write_text(
        json.dumps(
            {
                "source_runtime_commit": REVISION,
                "archives": archives,
                "probes": records,
                "scope": "Single-seed short functional probes, not a learning campaign or controlled throughput benchmark. Original pre-commit candidate provenance is preserved and runtime equivalence established post hoc. The 500-client HierFL probe overlaps unrelated test startup and is excluded from elapsed-time comparisons. No failed probe is relabelled as completed.",
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(records, indent=2))


if __name__ == "__main__":
    main()
