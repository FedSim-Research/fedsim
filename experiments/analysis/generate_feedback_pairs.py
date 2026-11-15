"""Expose every paired feedback contrast from the verified six-run evidence."""

import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--paper", type=Path, required=True)
paper = parser.parse_args().paper.resolve()
source = paper / "generated/lr-ablation-evidence.json"
evidence = json.loads(source.read_text(encoding="utf-8"))
runs = evidence["runs"]
assert len(runs) == 6 and evidence["paired_seeds"] == 3
lookup = {(row["placement"], row["seed"]): row for row in runs}
assert len(lookup) == 6
lines = [
    "% Generated from checked feedback evidence; all paired seeds retained.",
    r"\begin{table}[t]",
    r"\centering",
    r"\caption{Individual paired feedback effects ($\beta=0$ minus $0.05$), in accuracy percentage points. Interaction is concentrated minus balanced effect.}",
    r"\label{tab:feedback-pairs}",
    r"\begin{tabular}{rrrr}",
    r"\hline",
    r"Seed & Balanced & Concentrated & Interaction \\",
    r"\hline",
]
for seed in [42, 43, 44]:
    values = []
    for placement in ["balanced", "concentrated"]:
        row = lookup[placement, seed]
        effect = 100 * (row["ablation_accuracy"] - row["baseline_accuracy"])
        assert abs(effect - row["difference_pp"]) < 1e-10
        assert row["baseline_fit_dispatches"] == row["ablation_fit_dispatches"] == 14800
        assert row["baseline_delivered_updates"] == row["ablation_delivered_updates"] == 14600
        values.append(effect)
    interaction = values[1] - values[0]
    expected = next(row for row in evidence["paired_interaction"] if row["seed"] == seed)
    assert abs(interaction - expected["interaction_pp"]) < 1e-10
    lines.append(f"{seed} & {values[0]:+.2f} & {values[1]:+.2f} & {interaction:+.2f}" + r" \\")
lines.extend([r"\hline", r"\end{tabular}", r"\end{table}"])
(paper / "generated/feedback-pairs.tex").write_text("\n".join(lines) + "\n", encoding="utf-8")
(paper / "generated/feedback-pairs-provenance.json").write_text(
    json.dumps(
        {
            "source": source.name,
            "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            "scope": "Descriptive per-seed contrasts from the already accepted evidence; no new runs or independent samples.",
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
