"""Verify both archives before reporting the prospective feedback and placement follow-up."""

import argparse
import csv
import json
import math
import statistics as stats
from pathlib import Path

import matplotlib
from generate_population_results import (
    collect_work,
    mean_sd,
    require,
    verify_cohort_origins,
)
from generate_primary_results import digest, read, write_table

matplotlib.use("Agg")
from figure_style import BAND_ALPHA, FEEDBACK_DISABLED, SPYKER, finish, panels


class Archive:
    def __init__(self, root):
        self.root = root.resolve()
        self.manifest = read(self.root / "artifact-checksums.json")
        for name, expected in self.manifest.items():
            path = (self.root / name).resolve()
            require(path.is_relative_to(self.root), "Escaping manifest path")
            require(digest(path) == expected, "Checksum mismatch: " + name)
        require(
            self.get("completion-measurement.json")["status"] == "completed",
            "Incomplete archive",
        )
        require(
            self.get("measurements/measurement/execution.json")["status"] == "completed",
            "Incomplete execution",
        )
        self.cases = {
            case["key"]: case for case in self.get("inputs/measurement/plan.json")["cases"]
        }
        self.work = {}
        if "cohort-membership.json" in self.manifest:
            membership = verify_cohort_origins(self.manifest, self.get)
            for segment in membership["segments"]:
                self.work.update(
                    collect_work(
                        self.root / segment["runtime_log_directory"],
                        [self.cases[key] for key in segment["case_keys"]],
                    )
                )
        else:
            keys = self.get("inputs/measurement/selection.json")["selected_case_keys"]
            self.work = collect_work(
                self.root / "runtime/measurement/ray-logs",
                [self.cases[key] for key in keys],
            )

    def get(self, name):
        require(name in self.manifest, "Unverified input: " + name)
        return read(self.root / name)

    def endpoint(self, key):
        prefix = "measurements/measurement/" + key + "/"
        result = self.get(prefix + "result.json")
        points = sorted(self.get(prefix + "evaluations.json"), key=lambda p: p["virtual_time"])
        copies = self.get(prefix + "checkpoints.json")
        proof = self.get("evidence/measurement/" + key + "/verification.json")
        require(
            result["status"] == "completed" and result["architecture"] == "spyker",
            "Invalid endpoint",
        )
        require(
            result["seed"] == self.cases[key]["request"]["simulation_settings"]["seed"]
            and self.work[key]["unique_clients_delivered"] == 200,
            "Invalid seed or incomplete client participation",
        )
        child = result["runs"][0]["run_id"]
        require(
            [p["virtual_time"] for p in points] == list(range(0, 61, 10)),
            "Incomplete timeline",
        )
        require(all(p["run_id"] == child for p in points), "Mixed child identities")
        require(
            proof["run_id"] == child
            and proof["automatic_loki_exact_match"]
            and proof["periodic_points"] == 7,
            "Missing Loki proof",
        )
        evaluation = result["evaluation"]
        peers = evaluation["per_server"]
        require(len(peers) == 4 and set(peers) == set(copies), "Incomplete server evidence")
        require(evaluation["aggregation"] == "server_macro_mean", "Unexpected scope")
        for metric in ("accuracy", "avg_loss"):
            values = [peer[metric] for peer in peers.values()]
            require(all(math.isfinite(value) for value in values), "Nonfinite metric")
            require(
                math.isclose(evaluation[metric], stats.mean(values), abs_tol=1e-12),
                "Invalid macro mean",
            )
        for filename in copies.values():
            require(prefix + filename in self.manifest, "Unverified checkpoint")
        counters = points[-1]["server_stats"]["per_server"]
        require(set(counters) == set(peers), "Missing peer counters")
        require(
            all(peer["server_stats"]["sync_rounds_completed"] >= 1 for peer in counters.values()),
            "Inactive peer",
        )
        require(
            sum(peer["server_stats"]["total_client_updates"] for peer in counters.values())
            == self.work[key]["delivered_updates"],
            "Client trace and server counters differ",
        )
        return result, evaluation, points


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--primary", type=Path, required=True)
    parser.add_argument("--ablation", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    primary, ablation = Archive(args.primary), Archive(args.ablation)
    require(
        primary.get("source-record.json") == ablation.get("source-record.json"),
        "Different source/lock",
    )
    require(
        primary.get("dataset-provenance.json") == ablation.get("dataset-provenance.json"),
        "Different dataset",
    )
    require(
        primary.get("launch-preflight.json") == ablation.get("launch-preflight.json"),
        "Different image or resource budget",
    )
    partition_names = {
        name
        for name in primary.manifest
        if name.startswith("study-partitions/") and name.endswith(".json")
    }
    require(bool(partition_names), "Missing partition assignments")
    require(
        partition_names
        == {
            name
            for name in ablation.manifest
            if name.startswith("study-partitions/") and name.endswith(".json")
        },
        "Different partition evidence",
    )
    for name in partition_names:
        require(
            primary.manifest[name] == ablation.manifest[name],
            "Different planned partition assignment: " + name,
        )
    left = primary.get("inputs/measurement/config.json")
    right = ablation.get("inputs/measurement/config.json")
    left.pop("name")
    right.pop("name")
    require(
        left["spyker_config"]["decay_beta"] == 0.05 and right["spyker_config"]["decay_beta"] == 0,
        "Unexpected intervention",
    )
    left["spyker_config"]["decay_beta"] = 0
    require(left == right, "Uncontrolled configuration difference")
    selection = ablation.get("inputs/measurement/selection.json")
    require(
        selection["parent_plan_sha256"] == ablation.manifest["inputs/measurement/plan.json"],
        "Invalid parent selection",
    )
    placements = ["balanced", "concentrated"]
    seeds = [42, 43, 44]
    expected = [f"{placement}-spyker-seed{seed}" for placement in placements for seed in seeds]
    require(selection["selected_case_keys"] == expected, "Unexpected selected cases")
    amendment = ablation.get("PROTOCOL-AMENDMENT.json")
    require(
        amendment["before_any_feedback_intervention_run"] is True
        and amendment["selected_measurements"] == 6,
        "Missing prospective extension record",
    )
    from datetime import datetime

    calibration = ablation.get("measurements/calibration/balanced-hierfl-seed42/result.json")
    require(
        datetime.fromisoformat(amendment["recorded_at"])
        < datetime.fromisoformat(calibration["queued_at"]),
        "Extension was recorded after intervention execution",
    )
    rows, curves = (
        [],
        {
            (placement, regime): []
            for placement in placements
            for regime in ["baseline", "ablation"]
        },
    )
    for placement in placements:
        for seed in seeds:
            key = f"{placement}-spyker-seed{seed}"
            before, base, baseline_points = primary.endpoint(key)
            after, intervention, ablation_points = ablation.endpoint(key)
            curves[placement, "baseline"].append(baseline_points)
            curves[placement, "ablation"].append(ablation_points)
            require(before["seed"] == after["seed"] == seed, "Seed mismatch")
            require(before["run_id"] != after["run_id"], "Reused run")
            require(
                all(
                    math.isclose(
                        baseline_points[0][field],
                        ablation_points[0][field],
                        abs_tol=1e-10,
                    )
                    for field in ["accuracy", "loss"]
                ),
                "Different initial evaluation",
            )
            rows.append(
                {
                    "placement": placement,
                    "seed": seed,
                    "baseline_run": before["run_id"],
                    "ablation_run": after["run_id"],
                    "baseline_accuracy": base["accuracy"],
                    "ablation_accuracy": intervention["accuracy"],
                    "difference_pp": 100 * (intervention["accuracy"] - base["accuracy"]),
                    "baseline_loss": base["avg_loss"],
                    "ablation_loss": intervention["avg_loss"],
                    "baseline_fit_dispatches": primary.work[key]["fits"],
                    "ablation_fit_dispatches": ablation.work[key]["fits"],
                    "baseline_delivered_updates": primary.work[key]["delivered_updates"],
                    "ablation_delivered_updates": ablation.work[key]["delivered_updates"],
                    "ablation_minimum_updates_per_client": ablation.work[key][
                        "minimum_updates_per_client"
                    ],
                    "ablation_maximum_updates_per_client": ablation.work[key][
                        "maximum_updates_per_client"
                    ],
                }
            )
    grouped = {
        placement: [row for row in rows if row["placement"] == placement]
        for placement in placements
    }
    labels = {"balanced": "50/50/50/50", "concentrated": "140/20/20/20"}
    generated = args.paper / "generated"
    generated.mkdir(exist_ok=True)
    table = []
    per_placement = {}
    for placement in placements:
        selected = grouped[placement]
        per_placement[placement] = {
            "mean_difference_pp": stats.mean(row["difference_pp"] for row in selected),
            "sample_sd_difference_pp": stats.stdev(row["difference_pp"] for row in selected),
            "ablation_mean_accuracy": stats.mean(row["ablation_accuracy"] for row in selected),
            "ablation_accuracy_sample_sd": stats.stdev(
                row["ablation_accuracy"] for row in selected
            ),
        }
        for label, prefix in [
            (r"$\beta=0.05$", "baseline_"),
            (r"$\beta=0$", "ablation_"),
        ]:
            table.append(
                [
                    labels[placement],
                    label,
                    mean_sd([row[prefix + "accuracy"] for row in selected], 100),
                    mean_sd([row[prefix + "loss"] for row in selected], digits=3),
                ]
            )
    write_table(
        generated / "lr-ablation-results.tex",
        "Feedback-by-placement sensitivity with 200 clients and 60 virtual seconds: three paired seeds per cell; mean and sample SD. The balanced intervention was planned earlier; both placements were fixed before any intervention run.",
        "tab:lr-ablation",
        "llrr",
        ["Placement", "Feedback", "Accuracy (\\%)", "Loss"],
        table,
    )
    with (generated / "lr-ablation-values.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    interaction = []
    for seed in seeds:
        balanced = next(row for row in grouped["balanced"] if row["seed"] == seed)
        concentrated = next(row for row in grouped["concentrated"] if row["seed"] == seed)
        native_placement = 100 * (concentrated["baseline_accuracy"] - balanced["baseline_accuracy"])
        beta0_placement = 100 * (concentrated["ablation_accuracy"] - balanced["ablation_accuracy"])
        interaction.append(
            {
                "seed": seed,
                "native_placement_delta_pp": native_placement,
                "beta0_placement_delta_pp": beta0_placement,
                "interaction_pp": beta0_placement - native_placement,
            }
        )
    balanced, concentrated = per_placement["balanced"], per_placement["concentrated"]
    macros = {
        "LearningRateAblationDelta": f"{balanced['mean_difference_pp']:+.2f}",
        "LearningRateAblationSD": f"{balanced['sample_sd_difference_pp']:.2f}",
        "LearningRateAblationAccuracy": f"{100 * balanced['ablation_mean_accuracy']:.2f}",
        "LearningRateAblationConcentratedDelta": f"{concentrated['mean_difference_pp']:+.2f}",
        "LearningRateAblationConcentratedSD": f"{concentrated['sample_sd_difference_pp']:.2f}",
        "LearningRateAblationConcentratedAccuracy": f"{100 * concentrated['ablation_mean_accuracy']:.2f}",
        "LearningRateAblationPlacementDelta": f"{stats.mean(row['beta0_placement_delta_pp'] for row in interaction):+.2f}",
        "LearningRateAblationPlacementSD": f"{stats.stdev(row['beta0_placement_delta_pp'] for row in interaction):.2f}",
        "FeedbackInteractionDelta": f"{stats.mean(row['interaction_pp'] for row in interaction):+.2f}",
        "FeedbackInteractionSD": f"{stats.stdev(row['interaction_pp'] for row in interaction):.2f}",
    }
    (generated / "lr-ablation-numbers.tex").write_text(
        "\n".join("\\newcommand{\\" + key + "}{" + value + "}" for key, value in macros.items())
        + "\n",
        encoding="utf-8",
    )
    summary = {
        "primary_archive": str(primary.root),
        "primary_archive_manifest_sha256": digest(primary.root / "artifact-checksums.json"),
        "feedback_archive": str(ablation.root),
        "feedback_archive_manifest_sha256": digest(ablation.root / "artifact-checksums.json"),
        "paired_seeds": 3,
        "selected_measurements": 6,
        "mean_difference_pp": balanced["mean_difference_pp"],
        "sample_sd_difference_pp": balanced["sample_sd_difference_pp"],
        "per_placement": per_placement,
        "paired_interaction": interaction,
        "protocol_amendment": amendment,
        "scope": "Balanced-only intervention recorded earlier, prospectively extended before any intervention execution to both placements. Three paired seeds per cell; native policies and asynchronous order variability remain. No significance or universal-optimality claim.",
        "source": primary.get("source-record.json"),
        "verified_primary_files": len(primary.manifest),
        "verified_ablation_files": len(ablation.manifest),
        "execution_segments": ablation.get("cohort-membership.json")
        if "cohort-membership.json" in ablation.manifest
        else None,
        "runs": rows,
    }
    (generated / "lr-ablation-evidence.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    figures = args.paper / "figures"
    figures.mkdir(exist_ok=True)
    figure, axes = panels()
    for axis, placement in zip(axes, placements, strict=True):
        for name, label, color in [
            ("baseline", r"$\beta=0.05$", SPYKER),
            ("ablation", r"$\beta=0$", FEEDBACK_DISABLED),
        ]:
            series = curves[placement, name]
            times = [point["virtual_time"] for point in series[0]]
            values = [[100 * run[index]["accuracy"] for run in series] for index in range(7)]
            means, sd = (
                [stats.mean(value) for value in values],
                [stats.stdev(value) for value in values],
            )
            axis.plot(
                times,
                means,
                label=label,
                color=color,
                marker="s" if name == "baseline" else "D",
                linestyle="-" if name == "baseline" else "--",
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
        "lr-ablation-curves",
        accuracy_limit=40,
    )
    print(json.dumps({key: value for key, value in summary.items() if key != "runs"}, indent=2))


if __name__ == "__main__":
    main()
