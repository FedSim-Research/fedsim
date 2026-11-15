"""Audit the available same-seed operational repeats; never pool them as new seeds."""

import argparse
import json
from pathlib import Path

from generate_population_results import require
from generate_primary_results import digest, read


def verified_archive(root):
    root = root.resolve()
    manifest = read(root / "artifact-checksums.json")
    for name, expected in manifest.items():
        path = (root / name).resolve()
        require(
            path.is_relative_to(root) and digest(path) == expected,
            "Checksum mismatch: " + name,
        )

    def get(name):
        require(name in manifest, "Unverified input: " + name)
        return read(root / name)

    return manifest, get


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interrupted", type=Path, required=True)
    parser.add_argument("--restarted", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    before_manifest, before = verified_archive(args.interrupted)
    after_manifest, after = verified_archive(args.restarted)
    require(
        before("completion-measurement.json")["status"] == "failed",
        "Expected interrupted original campaign",
    )
    require(
        after("completion-measurement.json")["status"] == "completed",
        "Replacement campaign incomplete",
    )
    require(
        before("source-record.json") == after("source-record.json"),
        "Different source/lock",
    )
    for name in [
        "inputs/measurement/plan.json",
        "dataset-provenance.json",
        "launch-preflight.json",
    ]:
        require(
            before_manifest[name] == after_manifest[name],
            "Configured inputs differ: " + name,
        )
    available = before("EXCLUDED-ATTEMPT.json")["completed_measurements"]
    require(
        {entry["case"] for entry in available}
        == {"balanced-hierfl-seed42", "balanced-spyker-seed42"},
        "Unexpected available operational repeats",
    )
    records, macros = [], {}
    for method, suffix, checkpoints in [("hierfl", "Hier", 1), ("spyker", "Spyker", 4)]:
        key = "balanced-" + method + "-seed42"
        prefix = "measurements/measurement/" + key + "/"
        left, right = before(prefix + "result.json"), after(prefix + "result.json")
        for get, result, manifest in [
            (before, left, before_manifest),
            (after, right, after_manifest),
        ]:
            require(
                result["status"] == "completed"
                and result["seed"] == 42
                and result["architecture"] == method,
                "Incomplete or mismatched repeated case",
            )
            require(
                result["current_sim_time"] == result["run_time_limit"] == 60,
                "Different horizon",
            )
            proof = get("evidence/measurement/" + key + "/verification.json")
            require(
                proof["automatic_loki_exact_match"] and proof["periodic_points"] == 7,
                "Incomplete repeat evidence",
            )
            require(
                proof["run_id"] == result["runs"][0]["run_id"],
                "Repeat evidence identity mismatch",
            )
            copies = get(prefix + "checkpoints.json")
            require(
                len(copies) == checkpoints,
                "Incomplete repeated checkpoints",
            )
            require(
                all(prefix + filename in manifest for filename in copies.values()),
                "Missing repeated checkpoint file",
            )
        require(left["run_id"] != right["run_id"], "Run identity reused")
        delta = 100 * (right["evaluation"]["accuracy"] - left["evaluation"]["accuracy"])
        records.append(
            {
                "method": method,
                "seed": 42,
                "interrupted_campaign_completed_case_run_id": left["run_id"],
                "restarted_run_id": right["run_id"],
                "original_accuracy": left["evaluation"]["accuracy"],
                "restarted_accuracy": right["evaluation"]["accuracy"],
                "difference_pp": delta,
            }
        )
        macros["Operational" + suffix + "ReplayAbsoluteDifference"] = f"{abs(delta):.2f}"
    generated = args.paper / "generated"
    generated.mkdir(exist_ok=True)
    summary = {
        "source": before("source-record.json"),
        "original_files_verified": len(before_manifest),
        "restarted_files_verified": len(after_manifest),
        "records": records,
        "scope": "One available same-seed contrast per method caused by an operational restart, not a controlled replay campaign. Source, input plan, dataset and declared resource budget agree; actual scheduling and concurrent host activity need not. Excluded from primary means and seed counts; no estimate of general replay variance or causal isolation.",
    }
    (generated / "operational-repeat-evidence.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    (generated / "operational-repeat-numbers.tex").write_text(
        "\n".join("\\newcommand{\\" + name + "}{" + value + "}" for name, value in macros.items())
        + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
