"""Plan or execute sequential campaigns through the existing FedSim HTTP API."""

import argparse
import hashlib
import json
import logging
import math
import re
import shutil
import subprocess
import time
from dataclasses import asdict
from datetime import datetime, timezone
from itertools import combinations
from pathlib import Path
from typing import Annotated, Literal
from uuid import NAMESPACE_URL, uuid4, uuid5

import requests
from pydantic import BaseModel, ConfigDict, Field, model_validator

from fedsim.simulation.spyker_config import SpykerAlgorithmConfig

PositiveInt = Annotated[int, Field(strict=True, gt=0)]
PositiveFloat = Annotated[float, Field(gt=0, allow_inf_nan=False)]
NonnegativeInt = Annotated[int, Field(strict=True, ge=0)]
Name = Annotated[str, Field(pattern=r"^[a-z][a-z0-9-]{0,39}$")]


class NetworkProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    client_upload_mbps: list[PositiveFloat]
    client_download_mbps: list[PositiveFloat]
    server_upload_mbps: list[PositiveFloat]
    server_download_mbps: list[PositiveFloat]
    client_latency_ms: list[NonnegativeInt]
    server_latency_ms: NonnegativeInt


class SpykerParameters(BaseModel):
    """Explicit campaign parameters; omitted profiles retain the engine defaults."""

    model_config = ConfigDict(extra="forbid")

    decay_beta: Annotated[float, Field(ge=0, allow_inf_nan=False)]
    decay_mode: Literal["absolute", "relative"] = "absolute"
    staleness_mode: Literal["reciprocal", "none", "delta"] = "reciprocal"
    min_learning_rate: PositiveFloat
    h_inter: PositiveInt | Literal["auto"]
    h_intra: PositiveInt
    sigmoid_phi: PositiveFloat
    server_learning_rate: PositiveFloat
    tcp_rto_delay: Annotated[float, Field(ge=0, allow_inf_nan=False)]


class CampaignConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    name: Name
    phase: Literal["calibration", "measurement"]
    seeds: list[Annotated[int, Field(strict=True, ge=0)]]
    scenarios: dict[Name, list[PositiveInt]]
    network: NetworkProfile
    run_time_limit: PositiveFloat
    eval_interval: PositiveFloat
    epochs: PositiveInt
    lr: PositiveFloat
    batch_size: PositiveInt
    model_complexity: PositiveFloat
    client_compute_factor: PositiveFloat
    spyker_config: SpykerParameters | None = None
    require_peer_exchange: Annotated[bool, Field(strict=True)] | None = None

    @model_validator(mode="after")
    def validate_comparison(self):
        if not self.seeds or len(set(self.seeds)) != len(self.seeds):
            raise ValueError("campaign_requires_distinct_seeds")
        if not self.scenarios or len({sum(c) for c in self.scenarios.values()}) != 1:
            raise ValueError("campaign_requires_equal_client_totals")
        if len({len(c) for c in self.scenarios.values()}) != 1:
            raise ValueError("campaign_requires_equal_server_counts")
        server_count = len(next(iter(self.scenarios.values())))
        if server_count == 0:
            raise ValueError("campaign_requires_servers")
        if self.require_peer_exchange and server_count < 2:
            raise ValueError("campaign_peer_exchange_requires_multiple_servers")
        for field, values in self.network.model_dump().items():
            if field != "server_latency_ms" and len(values) != server_count:
                raise ValueError("campaign_network_region_count_mismatch")
        if self.phase == "calibration" and (len(self.seeds) != 1 or len(self.scenarios) != 1):
            raise ValueError("calibration_requires_one_seed_and_scenario")
        if self.eval_interval > self.run_time_limit:
            raise ValueError("campaign_interval_exceeds_duration")
        return self


def _write_json(path: Path, value) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    # Windows readers/antivirus can briefly deny replacement on bind mounts.
    # Retry only the atomic filesystem operation; HTTP submissions stay single-shot.
    started, delay, retries = None, 0.05, 0
    while True:
        try:
            temporary.replace(path)
            if retries:
                logging.getLogger(__name__).warning(
                    "Archive replacement recovered after %s retries: %s", retries, path
                )
            return
        except PermissionError:
            if started is None:
                started = time.monotonic()
            remaining = 8 - (time.monotonic() - started)
            if remaining <= 0:
                raise
            time.sleep(min(delay, remaining))
            delay = min(0.5, delay * 1.5)
            retries += 1


def _topology(
    counts: list[int], architecture: str, namespace: str, network: NetworkProfile
) -> dict:
    nodes, edges = [], []

    def node(key, kind, **extra):
        identity = str(uuid5(NAMESPACE_URL, f"{namespace}/{key}"))
        config = {
            "name": key,
            "computeFactor": 1000.0,
            "performanceSigma": 0.0,
            "uploadMbps": 100.0,
            "downloadMbps": 100.0,
            **extra,
        }
        nodes.append(
            {
                "id": identity,
                "type": kind,
                "point": {"x": len(nodes) * 150, "y": 0},
                "data": {"type": kind, "config": config},
            }
        )
        return identity

    def edge(source, target, latency):
        edges.append(
            {
                "id": str(len(edges)),
                "source": source,
                "target": target,
                "config": {
                    "pingMs": latency,
                    "jitterMs": 0,
                    "packetloss": 0.0,
                    "packetlossStddev": 0.0,
                },
            }
        )

    root = node("coordinator", "SuperServerNode") if architecture == "hierfl" else None
    servers = [
        node(
            f"server-{i + 1}",
            "ServerNode",
            uploadMbps=network.server_upload_mbps[i],
            downloadMbps=network.server_download_mbps[i],
        )
        for i in range(len(counts))
    ]
    if root:
        for server in servers:
            edge(server, root, network.server_latency_ms)
    else:
        for first, second in combinations(servers, 2):
            edge(first, second, network.server_latency_ms)
    for index, (server, count) in enumerate(zip(servers, counts, strict=True)):
        client = node(
            f"clients-{index + 1}",
            "ClientNode",
            count=count,
            type="workstation",
            uploadMbps=network.client_upload_mbps[index],
            downloadMbps=network.client_download_mbps[index],
        )
        edge(client, server, network.client_latency_ms[index])
    return {"nodes": nodes, "edges": edges}


def build_plan(config: CampaignConfig, campaign_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", campaign_id):
        raise ValueError("campaign_invalid_id")
    cases = []
    for scenario, counts in config.scenarios.items():
        for index, seed in enumerate(config.seeds):
            # Alternate order to reduce systematic first-run/cache effects.
            architectures = ("hierfl", "spyker") if index % 2 == 0 else ("spyker", "hierfl")
            for architecture in architectures:
                key = f"{scenario}-{architecture}-seed{seed}"
                graph = _topology(counts, architecture, f"{campaign_id}/{key}", config.network)
                for node in graph["nodes"]:
                    if node["type"] == "ClientNode":
                        node["data"]["config"]["computeFactor"] = config.client_compute_factor
                cases.append(
                    {
                        "key": key,
                        "architecture": architecture,
                        "scenario": scenario,
                        "graph": graph,
                        "request": {
                            "training_config": {
                                "epochs": config.epochs,
                                "lr": config.lr,
                                "batch_size": config.batch_size,
                                "model_complexity": config.model_complexity,
                            },
                            "simulation_settings": {
                                "dataset": "uoft-cs/cifar10",
                                "seed": seed,
                                "seed_set": [seed],
                                "repetitions": 1,
                                "gpu_budget": 0.0,
                                "run_time_limit": config.run_time_limit,
                                "eval_interval": config.eval_interval,
                                "idle_token_delay": 1.0,
                                "evaluate_model": True,
                                "output_filename": f"campaigns/{campaign_id}/{key}/model.pth",
                            },
                            "spyker_config": (
                                config.spyker_config.model_dump()
                                if config.spyker_config is not None
                                else asdict(SpykerAlgorithmConfig())
                            )
                            if architecture == "spyker"
                            else None,
                        },
                    }
                )
                if config.require_peer_exchange is not None:
                    cases[-1]["require_peer_exchange"] = config.require_peer_exchange
    return {
        "schema_version": 1,
        "campaign_id": campaign_id,
        # Keep saved v1 plans without the optional controls byte-compatible.
        "config": config.model_dump(exclude_none=True),
        "cases": cases,
    }


def read_plan(path: Path) -> dict:
    return _validated_plan(json.loads(path.read_bytes()))


def _validated_plan(plan: dict) -> dict:
    config = CampaignConfig.model_validate(plan["config"])
    if plan != build_plan(config, plan["campaign_id"]):
        raise ValueError("campaign_plan_does_not_match_configuration")
    return plan


def _calibration_review(path: Path, config: CampaignConfig) -> dict:
    review = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(review.get("rationale"), str) or not review["rationale"].strip():
        raise ValueError("campaign_calibration_requires_rationale")
    for field in ("run_time_limit", "eval_interval"):
        if review.get(field) != getattr(config, field):
            raise ValueError("campaign_calibration_decision_mismatch")
    archive = (path.parent / review["pilot_archive"]).resolve()
    checksum_bytes = (archive / "checksums.json").read_bytes()
    checksums = json.loads(checksum_bytes)
    records = {}
    if not {"plan.json", "execution.json"} <= checksums.keys():
        raise ValueError("campaign_calibration_missing_archive_evidence")
    for name, checksum in checksums.items():
        artifact = (archive / name).resolve()
        if not artifact.is_relative_to(archive):
            raise ValueError("campaign_calibration_artifact_outside_archive")
        content = artifact.read_bytes()
        if hashlib.sha256(content).hexdigest() != checksum:
            raise ValueError("campaign_calibration_checksum_mismatch")
        if artifact.suffix == ".json":
            records[name] = json.loads(content)
    pilot = _validated_plan(records["plan.json"])
    execution = records["execution.json"]
    if pilot["config"]["phase"] != "calibration" or execution.get("status") != "completed":
        raise ValueError("campaign_requires_completed_calibration")
    if [case.get("case") for case in execution.get("cases", [])] != [
        case["key"] for case in pilot["cases"]
    ] or any(case.get("status") != "completed" for case in execution["cases"]):
        raise ValueError("campaign_calibration_incomplete_cases")
    for case in pilot["cases"]:
        prefix = case["key"] + "/"
        required = {
            prefix + name
            for name in ("result.json", "evaluations.json", "definition.json", "checkpoints.json")
        }
        if not required <= checksums.keys():
            raise ValueError("campaign_calibration_missing_archive_evidence")
        result = records[prefix + "result.json"]
        if result.get("status") != "completed":
            raise ValueError("campaign_calibration_incomplete_result")
        points = records[prefix + "evaluations.json"]
        _check_result(result, case, points)
        _check_definition(records[prefix + "definition.json"], case)
        copies = records[prefix + "checkpoints.json"]
        expected = set(result.get("server_checkpoints") or {"coordinator": None})
        if set(copies) != expected or any(
            prefix + name not in checksums for name in copies.values()
        ):
            raise ValueError("campaign_calibration_missing_checkpoints")
    # Horizons may change after calibration; training and network conditions may not.
    for field in (
        "network",
        "epochs",
        "lr",
        "batch_size",
        "model_complexity",
        "client_compute_factor",
        "spyker_config",
        "require_peer_exchange",
    ):
        if pilot["config"].get(field) != config.model_dump().get(field):
            raise ValueError("campaign_calibration_conditions_mismatch")
    if next(iter(pilot["config"]["scenarios"].values())) not in config.scenarios.values():
        raise ValueError("campaign_calibration_topology_mismatch")
    return {
        **review,
        "pilot_archive": str(archive),
        "pilot_campaign_id": pilot["campaign_id"],
        "pilot_checksums_sha256": hashlib.sha256(checksum_bytes).hexdigest(),
    }


def _source_record(repo: Path) -> dict:
    def git(*args):
        return subprocess.check_output(["git", "-C", str(repo), *args])

    if git("status", "--porcelain").strip():
        raise ValueError("campaign_requires_clean_committed_source")
    return {
        "source_commit": git("rev-parse", "HEAD").decode().strip(),
        "uv_lock_sha256": hashlib.sha256((repo / "uv.lock").read_bytes()).hexdigest(),
    }


def _validate_environment(environment: dict, source: dict) -> None:
    for key in ("source_commit", "uv_lock_sha256"):
        if environment.get(key) != source[key]:
            raise ValueError(f"backend_{key}_does_not_match_source")
    for key in ("runtime_versions", "hardware", "resource_budget", "dataset_provenance"):
        if not isinstance(environment.get(key), dict) or not environment[key]:
            raise ValueError(f"backend_environment_missing_{key}")


def _request(client, method, url, **kwargs):
    # Only reads may be repeated. A failed POST may already have been accepted.
    attempts = 3 if method == "GET" else 1
    for attempt in range(attempts):
        try:
            response = client.request(method, url, timeout=30, **kwargs)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt + 1 == attempts:
                raise
            logging.getLogger(__name__).warning(
                "campaign_read_retry attempt=%d error=%s", attempt + 1, type(exc).__name__
            )
            time.sleep(0.2)
            continue
        response.raise_for_status()
        return response


def _check_definition(metadata: dict, case: dict) -> None:
    definition = metadata["definition"]
    canonical = json.dumps(
        definition, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    if hashlib.sha256(canonical.encode()).hexdigest() != metadata["sha256"]:
        raise ValueError("campaign_definition_checksum_mismatch")
    actual = definition["runs"][case["architecture"]]
    expected_nodes = [(n["id"], n["type"], n["data"]["config"]) for n in case["graph"]["nodes"]]
    actual_nodes = [(n["id"], n["type"], n["config"]) for n in actual["graph"]["nodes"]]
    expected_edges = [(e["source"], e["target"], e["config"]) for e in case["graph"]["edges"]]
    actual_edges = [
        (e["source_node_id"], e["target_node_id"], e["config"]) for e in actual["graph"]["edges"]
    ]
    # SQL may return edges in index order; node order controls partitions/token order.
    if actual_nodes != expected_nodes or sorted(actual_edges) != sorted(expected_edges):
        raise ValueError("campaign_submitted_topology_mismatch")
    for key in ("training_config", "simulation_settings", "spyker_config"):
        if case["request"][key] is None:
            continue
        for field, value in case["request"][key].items():
            if actual[key].get(field) != value:
                raise ValueError("campaign_submitted_settings_mismatch")


def _copy_checkpoints(
    result: dict, folder: Path, checkpoint_root: Path, backend_model_root: str
) -> None:
    # The default Compose mount maps backend paths to local var/models.
    from pathlib import PurePosixPath

    paths = result.get("server_checkpoints") or {"coordinator": result["output_filename"]}
    root = checkpoint_root.resolve()
    copied = {}
    for index, (server, filename) in enumerate(paths.items(), 1):
        relative = PurePosixPath(filename).relative_to(backend_model_root)
        source = (root / Path(*relative.parts)).resolve()
        if not source.is_relative_to(root):
            raise ValueError("campaign_checkpoint_outside_root")
        target = folder / f"checkpoint-{index}.pth"
        shutil.copyfile(source, target)
        copied[server] = target.name
    _write_json(folder / "checkpoints.json", copied)


def _check_result(result: dict, case: dict, points: list[dict]) -> None:
    evaluation = result.get("evaluation")
    if not evaluation or not points:
        raise ValueError("campaign_missing_evaluation_evidence")
    seed = case["request"]["simulation_settings"]["seed"]
    runs = result.get("runs") or []
    if len(runs) != 1 or runs[0].get("seed") != seed:
        raise ValueError("campaign_repetition_mismatch")
    metrics = [evaluation]
    if case["architecture"] == "spyker":
        peers = evaluation.get("per_server") or {}
        count = sum(n["type"] == "ServerNode" for n in case["graph"]["nodes"])
        if (
            evaluation.get("aggregation") != "server_macro_mean"
            or evaluation.get("server_count") != count
            or len(peers) != count
            or set(result.get("server_checkpoints") or {}) != set(peers)
        ):
            raise ValueError("campaign_missing_server_results")
        metrics.extend(peers.values())
        for field in ("accuracy", "avg_loss"):
            if not math.isclose(evaluation[field], sum(p[field] for p in peers.values()) / count):
                raise ValueError("campaign_server_mean_mismatch")
        if case.get("require_peer_exchange"):
            latest = max(points, key=lambda point: point["virtual_time"])
            details = latest.get("server_stats", {}).get("per_server", {})
            if set(details) != set(peers):
                raise ValueError("campaign_missing_peer_exchange_evidence")
            counters = [item.get("server_stats", {}) for item in details.values()]
            for item in counters:
                for field in (
                    "sync_rounds_initiated",
                    "sync_rounds_completed",
                    "peer_models_aggregated",
                ):
                    value = item.get(field)
                    if type(value) is not int or value < 0:
                        raise ValueError("campaign_missing_peer_exchange_evidence")
                if item["sync_rounds_completed"] < 1 or item["peer_models_aggregated"] < count - 1:
                    raise ValueError("campaign_missing_peer_exchange_evidence")
            if sum(item["sync_rounds_initiated"] for item in counters) < 1:
                raise ValueError("campaign_missing_peer_exchange_evidence")
    if any(not math.isfinite(m[field]) for m in metrics for field in ("accuracy", "avg_loss")):
        raise ValueError("campaign_nonfinite_metric")


def execute_plan(
    plan: dict,
    output: Path,
    api_url: str,
    *,
    checkpoint_root: Path,
    backend_model_root: str = "/var/lib/fedsim/models",
    client=None,
    poll_seconds: float = 2,
    timeout_seconds: float = 86400,
) -> None:
    client = client or requests.Session()
    base = api_url.rstrip("/")
    journal = {"status": "running", "cases": []}
    _write_json(output / "execution.json", journal)
    try:
        schema = _request(client, "GET", f"{base}/openapi.json").json()
        if "/runs/{run_id}/export/evaluations" not in schema.get("paths", {}):
            raise ValueError("campaign_backend_missing_evaluation_export")
        for case in plan["cases"]:
            target = checkpoint_root / case["request"]["simulation_settings"]["output_filename"]
            if target.parent.exists():
                raise ValueError("campaign_checkpoint_directory_already_exists")
        for case_index, case in enumerate(plan["cases"], 1):
            print(f"[{case_index}/{len(plan['cases'])}] {case['key']}", flush=True)
            folder = output / case["key"]
            folder.mkdir()
            entry = {"case": case["key"], "status": "creating_graph"}
            journal["cases"].append(entry)
            _write_json(output / "execution.json", journal)
            graph = _request(
                client,
                "POST",
                f"{base}/graphs/",
                json={
                    "name": f"{plan['campaign_id']} {case['key']}",
                    "architecture": case["architecture"],
                    "metadata": {"campaign_id": plan["campaign_id"]},
                },
            ).json()
            entry["graph_id"] = graph["graph_id"]
            _write_json(output / "execution.json", journal)
            graph_url = f"{base}/graphs/{graph['graph_id']}"
            graph_state = _request(client, "PUT", graph_url + "/state", json=case["graph"]).json()
            _write_json(folder / "graph.json", graph_state)
            payload = {**case["request"], "graph_id": graph["graph_id"]}
            _write_json(folder / "request.json", payload)
            entry["status"] = "submission_pending"
            _write_json(output / "execution.json", journal)
            accepted = _request(client, "POST", f"{base}/start_simulation", json=payload).json()
            _write_json(folder / "accepted.json", accepted)
            identity = accepted["run_id"]
            print(f"  accepted run_id={identity}", flush=True)
            entry.update(run_id=identity, status=accepted["status"])
            _write_json(output / "execution.json", journal)
            run_url = f"{base}/runs/{identity}"
            frozen = _request(client, "GET", run_url + "/export/definition").json()
            _write_json(folder / "definition.json", frozen)
            _check_definition(frozen, case)
            deadline = time.monotonic() + timeout_seconds
            while True:
                result = _request(client, "GET", run_url).json()
                _write_json(folder / "result.json", result)
                if result["status"] in {"completed", "failed"}:
                    break
                if time.monotonic() >= deadline:
                    raise TimeoutError(f"campaign_wait_expired: {identity}; backend may still run")
                time.sleep(poll_seconds)
            (folder / "summary.csv").write_bytes(
                _request(client, "GET", run_url + "/export/csv").content
            )
            points = _request(client, "GET", run_url + "/export/evaluations").json()
            _write_json(folder / "evaluations.json", points)
            entry["status"] = result["status"]
            _write_json(output / "execution.json", journal)
            if result["status"] != "completed":
                raise RuntimeError(f"campaign_run_failed: {identity}: {result.get('error')}")
            _check_result(result, case, points)
            _copy_checkpoints(result, folder, checkpoint_root, backend_model_root)
        journal["status"] = "completed"
    except BaseException as exc:
        journal.update(status="interrupted", error=str(exc))
        raise
    finally:
        _write_json(output / "execution.json", journal)
        _write_json(
            output / "checksums.json",
            {
                str(path.relative_to(output)).replace("\\", "/"): hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
                for path in sorted(output.rglob("*"))
                if path.is_file() and path.name != "checksums.json"
            },
        )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=["plan", "run"])
    inputs = parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--config", type=Path)
    inputs.add_argument("--plan", type=Path, help="Execute an unchanged, previously previewed plan")
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Plan only the first scenario and seed as a calibration pair",
    )
    parser.add_argument(
        "--calibration-review",
        type=Path,
        help="Required horizon/interval decision for measurement campaigns",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New local archive directory; existing paths are refused",
    )
    parser.add_argument("--api-url", default="http://localhost:8088/api")
    parser.add_argument("--environment", type=Path, help="Declared backend provenance JSON")
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument(
        "--checkpoint-root",
        type=Path,
        default=Path("var/models"),
        help="Local directory sharing the backend model files",
    )
    parser.add_argument("--backend-model-root", default="/var/lib/fedsim/models")
    args = parser.parse_args(argv)
    plan_bytes = None
    if args.plan:
        if args.mode != "run" or args.calibrate:
            parser.error("--plan requires run and cannot be combined with --calibrate")
        plan_bytes = args.plan.read_bytes()
        plan = _validated_plan(json.loads(plan_bytes))
        config = CampaignConfig.model_validate(plan["config"])
    else:
        config = CampaignConfig.model_validate_json(args.config.read_text(encoding="utf-8"))
        if args.calibrate:
            if args.mode != "plan":
                parser.error("--calibrate requires plan; execute the result with run --plan")
            config = CampaignConfig.model_validate(
                {
                    **config.model_dump(),
                    "phase": "calibration",
                    "seeds": config.seeds[:1],
                    "scenarios": dict(list(config.scenarios.items())[:1]),
                }
            )
        plan = build_plan(config, f"{config.name}-{uuid4().hex[:12]}")
    environment = source = None
    calibration = None
    if args.mode == "run":
        if args.environment is None:
            parser.error("run requires --environment with backend provenance")
        if config.phase == "measurement":
            if args.calibration_review is None:
                parser.error("measurement requires --calibration-review from a completed pilot")
            calibration = _calibration_review(args.calibration_review, config)
        source = _source_record(args.repo)
        environment = json.loads(args.environment.read_text(encoding="utf-8"))
        _validate_environment(environment, source)
    args.output.mkdir(parents=True, exist_ok=False)
    if args.plan:
        (args.output / "plan.json").write_bytes(plan_bytes)
    else:
        _write_json(args.output / "plan.json", plan)
    if calibration is not None:
        _write_json(args.output / "calibration-review.json", calibration)
    if args.mode == "run":
        _write_json(
            args.output / "environment.json",
            {
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "backend_declared": environment,
                "local_source": source,
                "api_url": args.api_url,
            },
        )
        archive = subprocess.check_output(
            ["git", "-C", str(args.repo), "archive", "--format=zip", source["source_commit"]]
        )
        (args.output / "source.zip").write_bytes(archive)
        execute_plan(
            plan,
            args.output,
            args.api_url,
            checkpoint_root=args.checkpoint_root,
            backend_model_root=args.backend_model_root,
        )
    print(f"{len(plan['cases'])} cases; archive: {args.output.resolve()}")


if __name__ == "__main__":
    main()
