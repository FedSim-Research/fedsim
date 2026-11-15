"""Conditional feedback-rule calculation; these are not measured training rates."""

import argparse
import ast
import hashlib
import json
import math
import statistics
import zipfile
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--archive", required=True, type=Path)
parser.add_argument("--output", required=True, type=Path)
args = parser.parse_args()
root = args.archive.resolve()
record = json.loads((root / "source-record.json").read_text())
manifest = json.loads((root / "input-checksums-measurement.json").read_text())
source_zip = root / "source.zip"
assert hashlib.sha256(source_zip.read_bytes()).hexdigest() == manifest["source.zip"]
with zipfile.ZipFile(source_zip) as archive:
    source = archive.read("src/fedsim/engines/spyker/server.py").decode()
tree = ast.parse(source)
server = next(
    node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "SpykerServer"
)
method = next(
    node
    for node in server.body
    if isinstance(node, ast.FunctionDef) and node.name == "_calculate_decay"
)
# Audit the assumed formula against the frozen method without executing archive code.
method.body = method.body[1:]  # Ignore the method's documentation string.
reference = ast.parse("""
def _calculate_decay(self, client_updates, avg_updates, base_lr):
    if client_updates < avg_updates:
        return base_lr
    decayed_lr = base_lr - (self.spyker_config.decay_beta * (client_updates - avg_updates))
    return max(self.spyker_config.min_learning_rate, decayed_lr)
""").body[0]
assert ast.dump(method) == ast.dump(reference), "Frozen feedback rule differs; re-audit derivation"
rows = []
for clients in [2, 20, 50, 140]:
    rates = []
    for j in range(1, clients + 1):
        value = max(1e-6, 0.01 - 0.05 * (4 - (3 + j / clients)))
        expected = max(1e-6, 0.01 - 0.05 * (1 - j / clients))
        assert math.isclose(value, expected, abs_tol=1e-15)
        rates.append(value)
    rows.append(
        {
            "active_clients": clients,
            "floor_assignments": sum(value == 1e-6 for value in rates),
            "mean_assigned_next_lr": statistics.mean(rates),
            "ordered_feedback_values": rates,
        }
    )
assert rows[2]["floor_assignments"] == 40
assert math.isclose(rows[2]["mean_assigned_next_lr"], 0.0011008, abs_tol=1e-15)
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(
    json.dumps(
        {
            "source": record,
            "scope": "Conditional calculation after AST-checking the frozen feedback method against the assumed rule; archive code is not executed. These are not observed runtime learning rates. Assume m established active clients begin with equal update counts3 and each contributes once. After contribution j, count4 minus active average(3+j/m) equals1-j/m. Fixed base LR.01, beta.05, floor1e-6.",
            "values": rows,
        },
        indent=2,
    )
    + "\n",
    encoding="utf-8",
)
print(
    json.dumps(
        [
            {key: value for key, value in row.items() if key != "ordered_feedback_values"}
            for row in rows
        ],
        indent=2,
    )
)
