"""Audit recorded positive peer-age jumps in the three frozen manuscript cohorts.

Read-only with respect to source repositories, manuscripts and raw archives.
No model reconstruction, causal attribution, extra repetitions or new experiments.
"""

import argparse
import ast
import csv
import hashlib
import io
import json
import re
import statistics
import zipfile
from collections import defaultdict
from pathlib import Path

LOCK_SHA256 = "4dad449b2c7a0cd60ef0d4409a705318f1981373eb58d1ede720ab29d13cd977"
SERVER_SOURCE_SHA256 = {
    "20d507096582de5b5055cb80127c14b15f3cf387": "a3287514217bdf2d019902b359971ecb2c19ab013703456b81837e499337537e",
    "2f724ba1767e2c03306282555857f8414f883df1": "a202402d661717c08a50561ca39e473ae8b7a747158eb1eaf5c5de36e81781bc",
}
FROZEN_EVIDENCE = {
    "population-evidence.json": {
        "manifest": "3e1c053766ada5396ae124fe5d1704aef67f432334e0d02d1cbda7d317eec1db",
        "source": "20d507096582de5b5055cb80127c14b15f3cf387",
    },
    "lr-ablation-evidence.json": {
        "manifest": "ab6bdb26b177ee449ccf77e3829ce32aa8123c993386f4ed94837ea25917b68c",
        "source": "20d507096582de5b5055cb80127c14b15f3cf387",
    },
    "primary-evidence.json": {
        "manifest": "9724e571870f7ba57b28b47bcbc73500af73394dddfd31aa9acf2df7cecd5dda",
        "source": "2f724ba1767e2c03306282555857f8414f883df1",
    },
}


def require(condition, message):
    if not condition:
        raise ValueError(message)


SOURCE_MEMBER = "src/fedsim/engines/spyker/server.py"
JUMP = re.compile(
    "\\[(?P<server>[0-9a-f-]{36})\\] Aggregated model from (?P<peer>[0-9a-f-]{36})\\. Age jumped (?P<old>\\d+) -> (?P<new>\\d+)"
)
BOOTSTRAP = re.compile(
    "\\[SpykerServer (?P<server>[0-9a-f-]{36})\\] Bootstrapping (?P<count>\\d+) clients\\."
)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def parse_positive_jump(line):
    """Parse one original print; ordinary log lines return None."""
    match = JUMP.fullmatch(line.strip())
    if match is None:
        return None
    before, after = int(match["old"]), int(match["new"])
    require(after > before, "Printed peer-age jump must be strictly positive")
    return {
        "server_id": match["server"],
        "peer_id": match["peer"],
        "old_age": before,
        "new_age": after,
        "absolute_jump": after - before,
        "relative_jump": (after - before) / before if before > 0 else None,
    }


def check_age_accounting(stats, events):
    """Check the last actor-local snapshot against all positive peer-age increments."""
    age, updates = stats["model_age"], stats["total_client_updates"]
    require(type(age) is int and age >= 0, "Invalid snapshot model age")
    require(type(updates) is int and updates >= 0, "Invalid snapshot client-update count")
    jumps = [event["absolute_jump"] for event in events]
    require(
        all(type(value) is int and value > 0 for value in jumps), "Invalid positive age increment"
    )
    total = sum(jumps)
    require(
        age == updates + total, "Model age does not match client updates plus recorded peer jumps"
    )
    return age, updates, total


def membership_segment(membership, case_key):
    """A retained case must belong to exactly one original execution segment."""
    keys = [key for segment in membership["segments"] for key in segment["case_keys"]]
    require(len(keys) == len(set(keys)), "Duplicate case membership across segments")
    matches = [segment for segment in membership["segments"] if case_key in segment["case_keys"]]
    require(len(matches) == 1, "Case is missing from retained segment membership")
    return matches[0]


def deduplicate_worker_logs(records):
    """Collapse exact copies or a byte-prefix capture of the same original worker file."""
    grouped = defaultdict(list)
    for record in records:
        require(sha(record["data"]) == record["sha256"], "Worker data digest mismatch")
        grouped[Path(record["path"]).name].append(record)
    chosen, aliases, seen_hashes = [], [], {}
    for basename, versions in sorted(grouped.items()):
        versions.sort(key=lambda row: (-len(row["data"]), row["path"]))
        selected = versions[0]
        for other in versions[1:]:
            require(
                selected["data"].startswith(other["data"]),
                f"Divergent copies of worker log {basename}",
            )
            aliases.append(
                {
                    "retained": selected["path"],
                    "excluded": other["path"],
                    "retained_sha256": selected["sha256"],
                    "excluded_sha256": other["sha256"],
                    "reason": "identical_file"
                    if selected["data"] == other["data"]
                    else "byte_prefix_of_retained_longest_capture",
                }
            )
        if selected["sha256"] in seen_hashes:
            aliases.append(
                {
                    "retained": seen_hashes[selected["sha256"]],
                    "excluded": selected["path"],
                    "reason": "identical_file",
                    "sha256": selected["sha256"],
                }
            )
        else:
            seen_hashes[selected["sha256"]] = selected["path"]
            chosen.append(selected)
    return chosen, aliases


def verify_source_contract(data):
    tree = ast.parse(data.decode("utf-8"))
    methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_handle_model_broadcast"
    ]
    require(len(methods) == 1, "Frozen age-audit input contract violated")
    method = methods[0]
    expected_test = ast.parse("self.model_age > old_age", mode="eval").body
    branches = [
        (index, node)
        for index, node in enumerate(method.body)
        if isinstance(node, ast.If) and ast.dump(node.test) == ast.dump(expected_test)
    ]
    require(len(branches) == 1, "Frozen age-audit input contract violated")
    print_index, branch = branches[0]
    require(
        len(branch.body) == 1 and (not branch.orelse), "Frozen age-audit input contract violated"
    )
    statement = branch.body[0]
    require(
        isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call),
        "Frozen age-audit input contract violated",
    )
    call = statement.value
    require(
        isinstance(call.func, ast.Name) and call.func.id == "print" and (len(call.args) == 1),
        "Frozen age-audit input contract violated",
    )
    message = call.args[0]
    require(isinstance(message, ast.JoinedStr), "Frozen age-audit input contract violated")
    require(
        [part.value for part in message.values if isinstance(part, ast.Constant)]
        == ["[", "] Aggregated model from ", ". Age jumped ", " -> "],
        "Frozen age-audit input contract violated",
    )
    require(
        [ast.unparse(part.value) for part in message.values if isinstance(part, ast.FormattedValue)]
        == ["self.server_id", "sender_id", "old_age", "self.model_age"],
        "Frozen age-audit input contract violated",
    )
    age_statements = []
    for expected in [
        "old_age = self.model_age",
        "weighted_age = (1.0 - effective_alpha) * self.model_age + effective_alpha * sender_age",
        "self.model_age = int(round(weighted_age))",
        "self.model_age = max(old_age, self.model_age)",
    ]:
        expected_ast = ast.dump(ast.parse(expected).body[0])
        indexes = [
            index for index, node in enumerate(method.body) if ast.dump(node) == expected_ast
        ]
        require(len(indexes) == 1, "Frozen age-audit input contract violated")
        age_statements.append(indexes[0])
    require(
        age_statements == sorted(age_statements) and age_statements[-1] < print_index,
        "Frozen age-audit input contract violated",
    )
    age_writes = []
    for function in [node for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]:
        for node in ast.walk(function):
            if not isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
                continue
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if any(
                (
                    isinstance(target, ast.Attribute) and ast.unparse(target) == "self.model_age"
                    for target in targets
                )
            ):
                age_writes.append({"method": function.name, "statement": ast.unparse(node)})
    require(
        age_writes
        == [
            {"method": "__init__", "statement": "self.model_age: int = 0"},
            {"method": "on_client_update", "statement": "self.model_age += 1"},
            {
                "method": "_handle_model_broadcast",
                "statement": "self.model_age = int(round(weighted_age))",
            },
            {
                "method": "_handle_model_broadcast",
                "statement": "self.model_age = max(old_age, self.model_age)",
            },
        ],
        "Frozen age-audit input contract violated",
    )
    return {
        "peer_handler_ast_sha256": sha(ast.dump(method).encode("utf-8")),
        "positive_branch_verified_by_ast": True,
        "all_model_age_writes_verified_by_ast": age_writes,
    }


class Archive:
    def __init__(self, root, evidence, evidence_key):
        self.root = Path(root).resolve()
        self.manifest_bytes = (self.root / "artifact-checksums.json").read_bytes()
        self.manifest = json.loads(self.manifest_bytes)
        reference = FROZEN_EVIDENCE[Path(evidence).name]
        self.expected_manifest = load(evidence)[evidence_key]
        require(
            self.expected_manifest == reference["manifest"], "Changed manuscript archive identity"
        )
        self.expected_source = reference["source"]
        require(
            sha(self.manifest_bytes) == self.expected_manifest,
            "Frozen age-audit input contract violated",
        )
        self.used = {}
        self.origins = {}
        self.segment_records = {}
        if "COHORT-ASSEMBLY.json" in self.manifest:
            assembly = self.json("COHORT-ASSEMBLY.json")
            self.origins = assembly["copied_files"]
            for segment in assembly["segments"]:
                sid = segment["id"]
                original = self.json(f"segments/{sid}/original-artifact-checksums.json")
                require(
                    sha(self.read(f"segments/{sid}/original-artifact-checksums.json"))
                    == segment["original_manifest_sha256"],
                    "Frozen age-audit input contract violated",
                )
                self.segment_records[sid] = {**segment, "original_manifest": original}

    def read(self, relative):
        relative = str(relative).replace("\\", "/")
        require(relative in self.manifest, f"Unmanifested input: {relative}")
        path = (self.root / relative).resolve()
        require(
            path.is_relative_to(self.root.resolve()), "Frozen age-audit input contract violated"
        )
        data = path.read_bytes()
        value = sha(data)
        require(value == self.manifest[relative], f"Input checksum mismatch: {relative}")
        self.used[relative] = value
        return data

    def json(self, relative):
        return json.loads(self.read(relative))

    def origin(self, relative, segment_id):
        if not self.origins:
            return None
        record = self.origins[relative]
        require(
            record["sha256"] == self.manifest[relative], "Frozen age-audit input contract violated"
        )
        segment = self.segment_records[segment_id]
        require(
            Path(record["source_archive"]).resolve() == Path(segment["root"]).resolve(),
            "Frozen age-audit input contract violated",
        )
        require(
            segment["original_manifest"][record["source_path"]] == record["sha256"],
            "Frozen age-audit input contract violated",
        )
        return record

    def source(self):
        record = self.json("source-record.json")
        archive_bytes = self.read("source.zip")
        with zipfile.ZipFile(io.BytesIO(archive_bytes)) as source:
            data = source.read(SOURCE_MEMBER)
            lock = source.read("uv.lock")
        require(record["source_commit"] == self.expected_source, "Unexpected producing revision")
        require(
            sha(data) == SERVER_SOURCE_SHA256[self.expected_source], "Changed frozen server source"
        )
        require(sha(lock) == LOCK_SHA256, "Changed frozen dependency lock")
        require(sha(lock) == record["uv_lock_sha256"], "Frozen age-audit input contract violated")
        contract = verify_source_contract(data)
        return {
            **record,
            "source_zip_sha256": sha(archive_bytes),
            "server_member": SOURCE_MEMBER,
            "server_source_sha256": sha(data),
            "server_matches_reviewed_git_export_sha256": True,
            **contract,
            "positive_branch_verified": "AST verifies the exact print fields inside the sole new_age>old_age branch, after old-age capture, weighted-age update, integer rounding and monotonic max, in _handle_model_broadcast.",
        }


def graph_servers(graph):
    nodes = {node["node_id"]: node for node in graph["nodes"]}
    servers = [node for node in graph["nodes"] if node["type"] == "ServerNode"]
    clients = {node["node_id"]: node for node in graph["nodes"] if node["type"] == "ClientNode"}
    assignments = defaultdict(list)
    for client_id, client in clients.items():
        neighbours = []
        for edge in graph["edges"]:
            left, right = (edge["source_node_id"], edge["target_node_id"])
            if left == client_id:
                neighbours.append(right)
            elif right == client_id:
                neighbours.append(left)
        require(
            len(neighbours) == 1 and nodes[neighbours[0]]["type"] == "ServerNode",
            "Frozen age-audit input contract violated",
        )
        assignments[neighbours[0]].append(client)
    return [
        {
            "server_id": server["node_id"],
            "server_ordinal": index + 1,
            "assigned_clients": sum(
                (int(node["config"]["count"]) for node in assignments[server["node_id"]])
            ),
            "client_group_ids": [node["node_id"] for node in assignments[server["node_id"]]],
        }
        for index, server in enumerate(servers)
    ]


def log_files(archive, log_directory, segment_id):
    records = []
    for relative in sorted(archive.manifest):
        if not (
            relative.startswith(log_directory + "/")
            and Path(relative).name.startswith("worker-")
            and relative.endswith(".out")
        ):
            continue
        data = archive.read(relative)
        archive.origin(relative, segment_id)
        records.append({"path": relative, "data": data, "sha256": sha(data)})
    return deduplicate_worker_logs(records)


def case_selection(archive, profiles):
    result = []
    membership = (
        archive.json("cohort-membership.json")
        if "cohort-membership.json" in archive.manifest
        else None
    )
    for profile in profiles:
        plan = archive.json(f"inputs/{profile}/plan.json")
        selected_keys = None
        if membership:
            selected_keys = {
                key for segment in membership["segments"] for key in segment["case_keys"]
            }
            require(
                selected_keys <= {case["key"] for case in plan["cases"]},
                "Unknown retained case in membership",
            )
        for case in plan["cases"]:
            if case["architecture"] != "spyker" or (
                selected_keys is not None and case["key"] not in selected_keys
            ):
                continue
            prefix = f"measurements/{profile}/{case['key']}"
            actual = archive.json(prefix + "/result.json")
            require(
                actual["status"] == "completed" and actual["architecture"] == "spyker",
                "Frozen age-audit input contract violated",
            )
            require(
                actual["seed"] == case["request"]["simulation_settings"]["seed"],
                "Frozen age-audit input contract violated",
            )
            captured = archive.json(prefix + "/graph.json")
            definition = archive.json(prefix + "/definition.json")
            normalized = {
                **{
                    key: value
                    for key, value in captured.items()
                    if key not in {"graph_id", "nodes", "edges"}
                },
                "id": captured["graph_id"],
                "nodes": [
                    {
                        **{
                            key: value
                            for key, value in node.items()
                            if key not in {"node_id", "graph_id"}
                        },
                        "id": node["node_id"],
                    }
                    for node in captured["nodes"]
                ],
                "edges": [
                    {
                        **{
                            key: value
                            for key, value in edge.items()
                            if key not in {"edge_id", "graph_id"}
                        },
                        "id": edge["edge_id"],
                    }
                    for edge in captured["edges"]
                ],
            }
            require(
                definition["definition"]["runs"]["spyker"]["graph"] == normalized,
                "Frozen age-audit input contract violated",
            )
            require(
                [node["node_id"] for node in captured["nodes"]]
                == [node["id"] for node in case["graph"]["nodes"]],
                "Frozen age-audit input contract violated",
            )
            require(
                [node["config"] for node in captured["nodes"]]
                == [node["data"]["config"] for node in case["graph"]["nodes"]],
                "Frozen age-audit input contract violated",
            )
            canonical = json.dumps(
                definition["definition"], sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
            require(
                sha(canonical) == definition["sha256"], "Frozen age-audit input contract violated"
            )
            segment = membership_segment(membership, case["key"]) if membership else None
            sid = segment["id"] if segment else profile
            log_directory = (
                segment["runtime_log_directory"] if segment else f"runtime/{profile}/ray-logs"
            )
            archive.origin(prefix + "/graph.json", sid)
            archive.origin(prefix + "/result.json", sid)
            servers = graph_servers(captured)
            require(
                set(actual["server_checkpoints"]) == {server["server_id"] for server in servers},
                "Frozen age-audit input contract violated",
            )
            evaluation_path = prefix + "/evaluations.json"
            periodic = archive.json(evaluation_path)
            endpoint = periodic[-1]
            expected_horizon = case["request"]["simulation_settings"]["run_time_limit"]
            require(
                endpoint["virtual_time"] == expected_horizon,
                "Frozen age-audit input contract violated",
            )
            require(
                endpoint["run_id"] in {run["run_id"] for run in actual["runs"]},
                "Frozen age-audit input contract violated",
            )
            require(
                set(endpoint["server_stats"]["per_server"])
                == {server["server_id"] for server in servers},
                "Frozen age-audit input contract violated",
            )
            archive.origin(evaluation_path, sid)
            result.append(
                {
                    "case": case["key"],
                    "profile": profile,
                    "segment": sid,
                    "scenario": case["scenario"],
                    "seed": actual["seed"],
                    "api_run_id": actual["run_id"],
                    "child_run_ids": [row["run_id"] for row in actual["runs"]],
                    "definition_sha256": definition["sha256"],
                    "log_directory": log_directory,
                    "servers": servers,
                    "graph_path": prefix + "/graph.json",
                    "result_path": prefix + "/result.json",
                    "last_periodic_evaluation_path": evaluation_path,
                    "last_periodic_evaluation": endpoint,
                }
            )
    return result


def audit(archive, label, profiles):
    source = archive.source()
    cases = case_selection(archive, profiles)
    directory_cases = defaultdict(list)
    for case in cases:
        directory_cases[case["log_directory"]].append(case)
    rows, events, duplicates, case_proof = ([], [], [], [])
    for directory, group in directory_cases.items():
        selected_servers = {}
        for case in group:
            for server in case["servers"]:
                require(
                    server["server_id"] not in selected_servers,
                    "Ambiguous server UUID across selected cases in one log directory",
                )
                selected_servers[server["server_id"]] = (case, server)
        logs, aliases = log_files(archive, directory, group[0]["segment"])
        duplicates.extend(aliases)
        evidence_by_server = defaultdict(list)
        bootstraps = defaultdict(list)
        for worker in logs:
            text = worker["data"].decode("utf-8", errors="strict")
            lines = text.splitlines()
            for line_number, line in enumerate(lines, 1):
                bootstrap = BOOTSTRAP.search(line)
                if bootstrap and bootstrap["server"] in selected_servers:
                    require(
                        ":actor_name:SpykerServer" in text,
                        "Frozen age-audit input contract violated",
                    )
                    bootstraps[bootstrap["server"]].append(
                        {
                            "path": worker["path"],
                            "sha256": worker["sha256"],
                            "line": line_number,
                            "clients": int(bootstrap["count"]),
                        }
                    )
                jump = parse_positive_jump(line)
                if jump and jump["server_id"] in selected_servers:
                    case, server = selected_servers[jump["server_id"]]
                    require(
                        jump["peer_id"] in {peer["server_id"] for peer in case["servers"]},
                        "Peer does not belong to captured case graph",
                    )
                    event = {
                        "cohort": label,
                        "profile": case["profile"],
                        "case": case["case"],
                        "segment": case["segment"],
                        "seed": case["seed"],
                        "server_ordinal": server["server_ordinal"],
                        "assigned_clients": server["assigned_clients"],
                        **jump,
                        "log_path": worker["path"],
                        "log_sha256": worker["sha256"],
                        "line_number": line_number,
                    }
                    evidence_by_server[server["server_id"]].append(event)
                    events.append(event)
        for case in group:
            case_rows = []
            for server in case["servers"]:
                sid = server["server_id"]
                require(
                    len(bootstraps[sid]) == 1,
                    f"Need one unique recorded server actor for {sid}: {bootstraps[sid]}",
                )
                require(
                    bootstraps[sid][0]["clients"] == server["assigned_clients"],
                    "Frozen age-audit input contract violated",
                )
                observed = evidence_by_server[sid]
                require(
                    all((event["log_path"] == bootstraps[sid][0]["path"] for event in observed)),
                    "Peer-age lines must belong to selected server's bootstrap actor",
                )
                max_absolute = max(observed, key=lambda event: event["absolute_jump"], default=None)
                positive_old = [event for event in observed if event["old_age"] > 0]
                max_relative = max(
                    positive_old, key=lambda event: event["relative_jump"], default=None
                )
                endpoint = case["last_periodic_evaluation"]
                server_endpoint = endpoint["server_stats"]["per_server"][sid]
                stats = server_endpoint["server_stats"]
                age, client_updates, sum_jumps = check_age_accounting(stats, observed)
                row = {
                    "cohort": label,
                    "profile": case["profile"],
                    "case": case["case"],
                    "segment": case["segment"],
                    "seed": case["seed"],
                    **server,
                    "positive_jumps_recorded": len(observed),
                    "minimum_positive_jump": min(
                        (event["absolute_jump"] for event in observed), default=None
                    ),
                    "max_absolute_jump": max_absolute["absolute_jump"] if max_absolute else 0,
                    "max_relative_jump_old_positive": max_relative["relative_jump"]
                    if max_relative
                    else None,
                    "positive_jumps_from_age_zero": sum(
                        (event["old_age"] == 0 for event in observed)
                    ),
                    "mean_recorded_absolute_jump": statistics.mean(
                        (event["absolute_jump"] for event in observed)
                    )
                    if observed
                    else None,
                    "initial_model_age": 0,
                    "last_periodic_virtual_time": endpoint["virtual_time"],
                    "last_periodic_snapshot_virtual_time": server_endpoint["snapshot_virtual_time"],
                    "last_periodic_model_age": age,
                    "last_periodic_total_client_updates": client_updates,
                    "sum_recorded_positive_age_jumps": sum_jumps,
                    "age_accounting_identity_matches": True,
                    "actor_log": bootstraps[sid][0],
                    "max_absolute_evidence": max_absolute,
                    "max_relative_evidence": max_relative,
                }
                rows.append(row)
                case_rows.append(sid)
            case_proof.append({**case, "server_actor_ids_verified": case_rows})
    return {
        "cohort": label,
        "archive": label,
        "manifest_sha256": archive.expected_manifest,
        "source": source,
        "accepted_spyker_cases": len(cases),
        "case_provenance": case_proof,
        "worker_log_deduplication": duplicates,
        "consumed_input_sha256": archive.used,
        "server_rows": rows,
        "recorded_positive_events": events,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--population", type=Path, required=True)
    parser.add_argument("--feedback", type=Path, required=True)
    parser.add_argument("--network", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    output = args.paper.resolve() / "generated"
    for archive in [args.population, args.feedback, args.network]:
        require(
            not output.is_relative_to(archive.resolve()), "Output must stay outside raw archives"
        )
    output.mkdir(parents=True, exist_ok=True)
    outputs = [
        audit(
            Archive(
                args.population, output / "population-evidence.json", "archive_manifest_sha256"
            ),
            "population200-native",
            ["measurement"],
        ),
        audit(
            Archive(
                args.feedback,
                output / "lr-ablation-evidence.json",
                "feedback_archive_manifest_sha256",
            ),
            "population200-beta0",
            ["measurement"],
        ),
        audit(
            Archive(args.network, output / "primary-evidence.json", "archive_manifest_sha256"),
            "network6-native",
            ["homogeneous", "heterogeneous"],
        ),
    ]
    require(
        [item["accepted_spyker_cases"] for item in outputs] == [6, 6, 12],
        "Incomplete accepted Spyker cohort selection",
    )
    rows = [row for output in outputs for row in output["server_rows"]]
    events = [event for output in outputs for event in output["recorded_positive_events"]]
    require(len(rows) == 84, "Incomplete captured server coverage")
    report = {
        "audit_script_sha256": sha(Path(__file__).read_bytes()),
        "analysis_type": "Retrospective descriptive analysis of original recorded stdout; not a predeclared experimental endpoint or new independent repetitions.",
        "scope": "Original manifest-bound stdout evidence of positive peer-induced model-age changes in accepted measured runs. No new learning runs and no modification of raw archives or manuscript.",
        "exclusions": "Calibration, unselected/failed cases and measurement segments outside selected case membership excluded. Identical file copies counted once; byte-prefix captures collapse only to verified longest version. No semantic line deduplication: repeated equal numeric events in one original actor log remain distinct observations.",
        "definitions": {
            "absolute_jump": "new_age-old_age",
            "relative_jump": "(new_age-old_age)/old_age, only where old_age>0",
            "zero_observed_events": "No positive-jump print recorded in the selected captured actor stdout; absence of lost logs is not independently attested.",
        },
        "age_accounting_crosscheck": "For every one of84servers, source-AST verified initialage0 and only client+=1/monotonicpeerage writes; last periodic model_age equals captured total_client_updates plus SUM(recorded positive peer-age jumps). This checks total age increments against an independently archived snapshot. Last periodic snapshots are actor-local, not final-checkpoint metadata or a global barrier; this is not independent runtime attestation.",
        "limits": "The print does not record peer pre-aggregation age, complete model payloads, individual client-reference ages or effective client blending coefficients. Cannot reconstruct per-update alpha, causality, equality of weights or a physical/virtual timestamp for every jump. Relative jumps summarize printed integer ages, not directly measured optimization effects. Zero recorded positive jumps does not imply absent peer exchange: equal/lower-age peer models can be aggregated without raising the monotonic integer age. Server instances are nested within three seeds per condition and are not independent seeded repetitions.",
        "archives": outputs,
    }
    write_json(output / "age-jump-audit.json", report)
    fields = [
        "cohort",
        "profile",
        "case",
        "segment",
        "seed",
        "server_id",
        "server_ordinal",
        "assigned_clients",
        "positive_jumps_recorded",
        "minimum_positive_jump",
        "max_absolute_jump",
        "max_relative_jump_old_positive",
        "positive_jumps_from_age_zero",
        "mean_recorded_absolute_jump",
        "initial_model_age",
        "last_periodic_virtual_time",
        "last_periodic_snapshot_virtual_time",
        "last_periodic_model_age",
        "last_periodic_total_client_updates",
        "sum_recorded_positive_age_jumps",
        "age_accounting_identity_matches",
    ]
    with (output / "age-jump-server-summary.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=fields, extrasaction="ignore", lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)
    with (output / "age-jump-events.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(events[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(events)
    summary = []
    grouped = defaultdict(list)
    for row in rows:
        scenario = row["case"].split("-spyker-seed")[0]
        grouped[row["cohort"], row["profile"], scenario, row["assigned_clients"]].append(row)
    for (cohort, profile, scenario, clients), values in sorted(grouped.items()):
        relative = [
            row["max_relative_jump_old_positive"]
            for row in values
            if row["max_relative_jump_old_positive"] is not None
        ]
        summary.append(
            {
                "cohort": cohort,
                "profile": profile,
                "scenario": scenario,
                "clients_per_server": clients,
                "server_instances": len(values),
                "positive_jumps_recorded": sum((row["positive_jumps_recorded"] for row in values)),
                "per_server_recorded_jump_counts": [
                    row["positive_jumps_recorded"] for row in values
                ],
                "maximum_absolute_jump": max((row["max_absolute_jump"] for row in values)),
                "minimum_positive_jump": min(
                    (
                        row["minimum_positive_jump"]
                        for row in values
                        if row["minimum_positive_jump"] is not None
                    ),
                    default=None,
                ),
                "maximum_relative_jump_old_positive": max(relative, default=None),
                "last_periodic_model_age_range": [
                    min((row["last_periodic_model_age"] for row in values)),
                    max((row["last_periodic_model_age"] for row in values)),
                ],
                "last_periodic_total_client_updates_range": [
                    min((row["last_periodic_total_client_updates"] for row in values)),
                    max((row["last_periodic_total_client_updates"] for row in values)),
                ],
                "sum_recorded_positive_age_jumps_range": [
                    min((row["sum_recorded_positive_age_jumps"] for row in values)),
                    max((row["sum_recorded_positive_age_jumps"] for row in values)),
                ],
                "all_age_accounting_identities_match": all(
                    (row["age_accounting_identity_matches"] for row in values)
                ),
            }
        )
    write_json(output / "age-jump-group-summary.json", summary)
    print(
        json.dumps(
            {
                "accepted_spyker_cases": sum((item["accepted_spyker_cases"] for item in outputs)),
                "server_rows": len(rows),
                "positive_events_recorded": len(events),
                "groups": summary,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
