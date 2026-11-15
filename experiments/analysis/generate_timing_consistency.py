"""Check the homogeneous virtual-cost model against complete primary traces."""

import argparse
import hashlib
import json
import math
import zipfile
from pathlib import Path


def digest(path):
    value = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(2**20), b""):
            value.update(chunk)
    return value.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--paper", type=Path, required=True)
    args = parser.parse_args()
    root = args.archive.resolve()
    manifest = json.loads((root / "artifact-checksums.json").read_text())

    def verified(name):
        path = (root / name).resolve()
        if not path.is_relative_to(root) or digest(path) != manifest[name]:
            raise ValueError("Unverified timing input: " + name)
        return json.loads(path.read_text(encoding="utf-8-sig"))

    evidence_path = args.paper / "generated/population-evidence.json"
    evidence = json.loads(evidence_path.read_text())
    assert evidence["runs"] == 12
    assert evidence["archive_manifest_sha256"] == digest(root / "artifact-checksums.json")
    config = verified("inputs/measurement/config.json")
    network = config["network"]
    for key in [
        "client_upload_mbps",
        "client_download_mbps",
        "server_upload_mbps",
        "server_download_mbps",
    ]:
        assert network[key] == [100] * 4
    assert network["client_latency_ms"] == [10] * 4 and network["server_latency_ms"] == 100
    assert config["epochs"] == config["model_complexity"] == 1
    assert config["client_compute_factor"] == 500 and config["run_time_limit"] == 60
    for seed in [42, 43, 44]:
        partitions = verified(f"study-partitions/seed-{seed}.json")
        assert partitions["partition_count"] == 200
        assert all(
            partition["train"]["rows"] == 200 and partition["test"]["rows"] == 50
            for partition in partitions["partitions"].values()
        )
    prefix = "measurements/measurement/balanced-hierfl-seed42/"
    copies = verified(prefix + "checkpoints.json")
    checkpoint = root / prefix / next(iter(copies.values()))
    assert digest(checkpoint) == manifest[checkpoint.relative_to(root).as_posix()]
    with zipfile.ZipFile(checkpoint) as archive:
        storages = [
            item
            for item in archive.infolist()
            if "/data/" in item.filename and item.filename.rsplit("/", 1)[1].isdigit()
        ]
        assert len(storages) == 10
        payload = sum(item.file_size for item in storages)
    client_period = 200 / 500 + 2 * (8 * payload / 10**8 + 0.01)
    hierarchical_period = client_period + 2 * (8 * payload / 10**8 + 0.1)
    expected = {
        "hierfl": math.floor(60 / hierarchical_period),
        "spyker": math.floor(60 / client_period),
    }
    checked = []
    for cell in evidence["cells"]:
        for run in cell["runs"]:
            captured = verified(f"measurements/measurement/{run['case']}/definition.json")
            canonical = json.dumps(
                captured["definition"],
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=False,
                allow_nan=False,
            )
            assert hashlib.sha256(canonical.encode()).hexdigest() == captured["sha256"]
            definition = captured["definition"]["runs"][cell["method"]]
            settings = definition["simulation_settings"]
            assert settings["run_time_limit"] == 60 and settings["gpu_budget"] == 0
            assert settings["seed"] == run["seed"]
            training = definition["training_config"]
            assert training["epochs"] == training["model_complexity"] == 1
            graph = definition["graph"]
            nodes = {node["id"]: node for node in graph["nodes"]}
            assert len(nodes) == len(graph["nodes"])
            clients = {identity for identity, node in nodes.items() if node["type"] == "ClientNode"}
            group_counts = [nodes[identity]["config"]["count"] for identity in clients]
            assert len(clients) == 4
            assert all(type(count) is int and count > 0 for count in group_counts)
            assert sum(group_counts) == 200
            for identity, node in nodes.items():
                attributes = node["config"]
                assert attributes["uploadMbps"] == attributes["downloadMbps"] == 100
                assert attributes["performanceSigma"] == 0
                if identity in clients:
                    assert attributes["computeFactor"] == 500
            for edge in graph["edges"]:
                source, target = edge["source_node_id"], edge["target_node_id"]
                assert source in nodes and target in nodes
                attributes = edge["config"]
                assert (
                    attributes["jitterMs"]
                    == attributes["packetloss"]
                    == attributes["packetlossStddev"]
                    == 0
                )
                assert attributes["pingMs"] == (
                    10 if source in clients or target in clients else 100
                )
            count = expected[cell["method"]]
            assert run["unique_clients_delivered"] == 200
            assert run["minimum_updates_per_client"] == run["maximum_updates_per_client"] == count
            assert run["delivered_updates"] == 200 * count
            checked.append(
                {
                    "case": run["case"],
                    "expected_updates_per_client": count,
                    "observed_minimum": run["minimum_updates_per_client"],
                    "observed_maximum": run["maximum_updates_per_client"],
                    "captured_definition_sha256": captured["sha256"],
                    "captured_client_groups": len(clients),
                    "captured_logical_clients": sum(group_counts),
                    "zero_noise_link_and_client_cost_controls_verified": True,
                }
            )
    report = {
        "source": evidence["source"],
        "archive_manifest_sha256": evidence["archive_manifest_sha256"],
        "population_evidence_sha256": digest(evidence_path),
        "model_payload_bytes": payload,
        "client_cycle_seconds": client_period,
        "hierarchical_round_seconds": hierarchical_period,
        "expected_updates_per_client": expected,
        "verified_cases": checked,
        "scope": "Internal consistency of the configured zero-noise, homogeneous, no-contention cost model, using planned partition sizes and actual per-client event counts. Does not calibrate against hardware or prove actor-level row assignments. Model byte envelope comes from the verified checkpoint tensor storages.",
    }
    generated = args.paper / "generated"
    (generated / "timing-consistency-evidence.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    macros = {
        "ModelPayloadBytes": f"{payload:,}".replace(",", "{,}"),
        "ClientCycleSeconds": f"{client_period:.5f}",
        "HierRoundSeconds": f"{hierarchical_period:.5f}",
        "HierExpectedUpdates": str(expected["hierfl"]),
        "SpykerExpectedUpdates": str(expected["spyker"]),
    }
    (generated / "timing-consistency-numbers.tex").write_text(
        "\n".join("\\newcommand{\\" + key + "}{" + value + "}" for key, value in macros.items())
        + "\n",
        encoding="utf-8",
    )
    print(
        json.dumps(
            {
                "verified_cases": len(checked),
                "payload_bytes": payload,
                "client_cycle_seconds": client_period,
                "hierarchical_round_seconds": hierarchical_period,
                "updates_per_client": expected,
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
