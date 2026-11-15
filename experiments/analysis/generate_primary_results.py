"""Generate manuscript tables and figures from the unchanged six-client archive."""

import argparse
import csv
import hashlib
import json
import math
import statistics as stats
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
from figure_style import BAND_ALPHA, HIERFL, SPYKER, finish, panels


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1048576), b""):
            h.update(block)
    return h.hexdigest()


def write_table(path, caption, label, columns, header, rows, wide=False):
    if label in {
        "tab:population-results",
        "tab:population-work",
        "tab:primary-results",
        "tab:capacity",
    }:
        wide = False
    if label == "tab:primary-results":
        header = ["Links", "Clients", "Method", "Accuracy (\\%)", "Loss"]
        caption += " Hom./Het.: homogeneous/heterogeneous links; H/S: HierFL/Spyker-inspired; clients: per-server allocation."
        aliases = {
            "Homogeneous": "Hom.",
            "Heterogeneous": "Het.",
            "HierFL": "H",
            "Spyker-inspired": "S",
        }
        rows = [[aliases.get(cell, cell) for cell in row] for row in rows]
    if label == "tab:population-work":
        header = ["Placement", "Method", "Fits", "Updates", "Rounds", "Merges"]
        caption = (
            "Observed work in the 200-client study. Counts are identical at all three seeds "
            "(sample SD zero). Fits include look-ahead calls; updates are delivered "
            "client contributions. Rounds count initiations; merges count peer models. "
            "H: HierFL; S: Spyker-inspired."
        )
        rows = [
            [
                "H"
                if cell == "HierFL"
                else "S"
                if cell == "Spyker-inspired"
                else cell.replace(r" $\pm$ 0", "")
                for cell in row
            ]
            for row in rows
        ]
    if label == "tab:capacity":
        header = ["Method", "Clients", "Workers", "Store", "Outcome", "RAM"]
        caption += " Store and RAM are in GiB; Async. denotes the Spyker-inspired engine."
        rows = [["Async." if cell == "Spyker-inspired" else cell for cell in row] for row in rows]
    env = "table*" if wide else "table"
    lines = [
        "% Generated from verified archives; do not edit numeric cells.",
        r"\begin{" + env + "}[t]",
        r"\centering",
        r"\caption{" + caption + "}",
        r"\label{" + label + "}",
        r"\setlength{\tabcolsep}{" + ("10pt" if wide else "3.5pt") + "}",
        r"\begin{tabular}{" + columns + "}",
        r"\hline",
        " & ".join(header) + r" \\",
        r"\hline",
    ]
    lines += [" & ".join(row) + r" \\" for row in rows]
    lines += [r"\hline", r"\end{tabular}", r"\end{" + env + "}"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    archive, paper = args.archive.resolve(), args.paper.resolve()
    assert read(archive / "completion.json")["status"] == "completed"
    checksums = read(archive / "artifact-checksums.json")
    for name, expected in checksums.items():
        path = (archive / name).resolve()
        assert path.is_relative_to(archive) and digest(path) == expected, name

    records, counters = [], []
    groups, timelines = defaultdict(list), defaultdict(list)
    configs = {}
    for network in ("homogeneous", "heterogeneous"):
        output = archive / "measurements" / network
        plan = read(output / "plan.json")
        configs[network] = plan["config"]
        assert read(output / "execution.json")["status"] == "completed"
        for case in plan["cases"]:
            folder = output / case["key"]
            result = read(folder / "result.json")
            points = sorted(read(folder / "evaluations.json"), key=lambda p: p["virtual_time"])
            assert [p["virtual_time"] for p in points] == [0, 60, 120, 180, 240, 300]
            assert result["status"] == "completed"
            key = network, case["scenario"], case["architecture"]
            record = {
                "network": network,
                "placement": case["scenario"],
                "method": case["architecture"],
                "seed": result["seed"],
                "accuracy": result["evaluation"]["accuracy"],
                "loss": result["evaluation"]["avg_loss"],
                "wall_seconds": result["duration_seconds"],
                "last_gain_pp": 100 * (points[-1]["accuracy"] - points[-2]["accuracy"]),
            }
            records.append(record)
            groups[key].append(record)
            timelines[key].append(points)
            if case["architecture"] == "spyker":
                peers = points[-1]["server_stats"]["per_server"]
                assert len(peers) == 3
                s = [p["server_stats"] for p in peers.values()]
                counters.append(
                    {
                        "network": network,
                        "placement": case["scenario"],
                        "seed": result["seed"],
                        "client_updates": sum(p["total_client_updates"] for p in s),
                        "initiated_rounds": sum(p["sync_rounds_initiated"] for p in s),
                        "accepted_peer_models": sum(p["peer_models_aggregated"] for p in s),
                    }
                )
    assert len(records) == 24
    for group in groups.values():
        assert sorted(r["seed"] for r in group) == [42, 43, 44]
    means = {key: stats.mean(r["accuracy"] for r in rows) for key, rows in groups.items()}
    for cell in read(archive / "analysis/summary.json")["cells"]:
        key = cell["profile"], cell["scenario"], cell["architecture"]
        assert math.isclose(means[key], cell["accuracy_mean"], abs_tol=1e-12)
        assert math.isclose(
            stats.stdev(r["accuracy"] for r in groups[key]),
            cell["accuracy_sample_sd"],
            abs_tol=1e-12,
        )

    generated, figures = paper / "generated", paper / "figures"
    generated.mkdir(exist_ok=True)
    figures.mkdir(exist_ok=True)
    rows = []
    for network in configs:
        for placement, counts in (("balanced", "2/2/2"), ("imbalanced", "4/1/1")):
            for method, label in (("hierfl", "HierFL"), ("spyker", "Spyker-inspired")):
                group = groups[network, placement, method]
                acc = [100 * r["accuracy"] for r in group]
                loss = [r["loss"] for r in group]
                rows.append(
                    [
                        network.capitalize(),
                        counts,
                        label,
                        f"\\({stats.mean(acc):.2f} \\pm {stats.stdev(acc):.2f}\\)",
                        f"\\({stats.mean(loss):.3f} \\pm {stats.stdev(loss):.3f}\\)",
                    ]
                )
    write_table(
        generated / "primary-results.tex",
        "Six-client network study after 300 virtual seconds. Mean and sample standard deviation over three seeds; accuracy SD is in percentage points. Spyker-inspired metrics are equal-weight means over three server models within each run.",
        "tab:primary-results",
        "lllll",
        [
            "Network",
            "Clients per server",
            "Method",
            r"Test accuracy (\%)",
            "Loss per example",
        ],
        rows,
        wide=True,
    )
    rows = []
    for field, label in [
        ("client_upload_mbps", "Client upload (Mbps)"),
        ("client_download_mbps", "Client download (Mbps)"),
        ("server_upload_mbps", "Server upload (Mbps)"),
        ("server_download_mbps", "Server download (Mbps)"),
        ("client_latency_ms", "Client link latency (ms)"),
    ]:
        values = ["/".join(f"{v:g}" for v in configs[n]["network"][field]) for n in configs]
        rows.append([label, *values])
    write_table(
        generated / "primary-network.tex",
        "Network profiles in server-group order. Bandwidth is a node property. All server-to-server links have 100 ms latency.",
        "tab:primary-network",
        "lll",
        ["Quantity", "Homogeneous", "Heterogeneous"],
        rows,
    )
    rows = []
    for network in configs:
        for placement, counts in (("balanced", "2/2/2"), ("imbalanced", "4/1/1")):
            group = [r for r in counters if r["network"] == network and r["placement"] == placement]
            values = []
            for field in ("client_updates", "initiated_rounds", "accepted_peer_models"):
                distinct = {r[field] for r in group}
                assert len(distinct) == 1, (network, placement, field)
                values.append(str(next(iter(distinct))))
            rows.append([network.capitalize(), counts, *values])
    write_table(
        generated / "primary-exchanges.tex",
        "Spyker-inspired counters at the last periodic evaluation, summed across servers. Each initiated round is counted once. Values agree across seeds in each cell.",
        "tab:primary-exchanges",
        "llrrr",
        ["Network", "Placement", "Updates", "Rounds", "Peer models"],
        rows,
    )

    contrasts = []
    for network in configs:
        for method in ("hierfl", "spyker"):
            balanced = {r["seed"]: r["accuracy"] for r in groups[network, "balanced", method]}
            changes = [
                100 * (r["accuracy"] - balanced[r["seed"]])
                for r in groups[network, "imbalanced", method]
            ]
            contrasts.append(
                {
                    "network": network,
                    "method": method,
                    "contrast": "4/1/1 minus 2/2/2",
                    "seed_differences_pp": changes,
                    "mean_pp": stats.mean(changes),
                    "sample_sd_pp": stats.stdev(changes),
                }
            )
    macros = {
        "SpykerHomPlacementDrop": -next(
            c["mean_pp"]
            for c in contrasts
            if c["network"] == "homogeneous" and c["method"] == "spyker"
        ),
        "SpykerHetPlacementDrop": -next(
            c["mean_pp"]
            for c in contrasts
            if c["network"] == "heterogeneous" and c["method"] == "spyker"
        ),
        "MinimumLastGain": min(r["last_gain_pp"] for r in records),
        "MaximumLastGain": max(r["last_gain_pp"] for r in records),
    }
    for prefix, network in (("Hom", "homogeneous"), ("Het", "heterogeneous")):
        for short, method in (("Hier", "hierfl"), ("Spy", "spyker")):
            for suffix, placement in (("Bal", "balanced"), ("Imb", "imbalanced")):
                macros["Primary" + prefix + short + suffix] = (
                    100 * means[network, placement, method]
                )
    (generated / "primary-numbers.tex").write_text(
        "\n".join(f"\\newcommand{{\\{key}}}{{{value:.2f}}}" for key, value in macros.items())
        + "\n",
        encoding="utf-8",
    )

    fig, axes = panels()
    for ax, network in zip(axes, configs):
        for method, color, label in [
            ("hierfl", HIERFL, "HierFL"),
            ("spyker", SPYKER, "Spyker-inspired"),
        ]:
            for placement, style, counts in [
                ("balanced", "-", "2/2/2"),
                ("imbalanced", "--", "4/1/1"),
            ]:
                runs = timelines[network, placement, method]
                times = [p["virtual_time"] for p in runs[0]]
                values = [[100 * run[i]["accuracy"] for run in runs] for i in range(6)]
                mean, sd = (
                    [stats.mean(v) for v in values],
                    [stats.stdev(v) for v in values],
                )
                ax.plot(
                    times,
                    mean,
                    style,
                    color=color,
                    label=label + " " + counts,
                    marker="o" if method == "hierfl" else "s",
                )
                ax.fill_between(
                    times,
                    [a - b for a, b in zip(mean, sd)],
                    [a + b for a, b in zip(mean, sd)],
                    color=color,
                    alpha=BAND_ALPHA,
                    linewidth=0,
                )
    finish(
        fig,
        axes,
        ["(a) Homogeneous links", "(b) Heterogeneous links"],
        300,
        figures,
        "primary-learning-curves",
        accuracy_limit=85,
    )

    status = read(archive / "status.json")
    hours = (
        datetime.fromisoformat(status["completed_at"])
        - datetime.fromisoformat(status["started_at"])
    ).total_seconds() / 3600
    evidence = {
        "source_commit": read(archive / "source-record.json")["source_commit"],
        "archive_manifest_sha256": digest(archive / "artifact-checksums.json"),
        "archive_files_verified": len(checksums),
        "primary_runs": len(records),
        "whole_campaign_wall_hours": hours,
        "contrasts": contrasts,
        "counter_rows": counters,
        "last_interval_accuracy_gain_pp_range": [
            macros["MinimumLastGain"],
            macros["MaximumLastGain"],
        ],
        "notes": "Calibration cases excluded. SD is across seeds. Fixed seeds do not establish deterministic event replay.",
    }
    (generated / "primary-evidence.json").write_text(
        json.dumps(evidence, indent=2) + "\n", encoding="utf-8"
    )
    with (generated / "primary-run-values.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    print(
        json.dumps(
            {
                "status": "passed",
                "archive_files_verified": len(checksums),
                "contrasts": contrasts,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
