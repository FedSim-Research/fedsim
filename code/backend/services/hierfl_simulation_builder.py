from __future__ import annotations

import json
import sys
from functools import lru_cache
from pathlib import Path
from typing import Any

from backend.db.models import Graph, Node, Edge

DEFAULT_RUN_TIME_LIMIT = 5000.0
MIN_PERF_STDDEV = 0.01


@lru_cache(maxsize=1)
def _import_hierfl():
    repo_root = Path(__file__).resolve().parents[3]
    impl_root = repo_root / "code" / "framework" / "impl"
    impl_path = str(impl_root)
    if impl_path not in sys.path:
        sys.path.append(impl_path)

    from main.main_hierarchical import HierarchicalSimulation, evaluate_model  # type: ignore
    from specs.performance_metrics import Performance  # type: ignore
    from specs.network_metrics import Network  # type: ignore

    return HierarchicalSimulation, Performance, Network, evaluate_model


def _node_config(node: Node) -> dict[str, Any]:
    if not node.config_json:
        return {}
    try:
        return json.loads(node.config_json)
    except json.JSONDecodeError:
        return {}


def _performance_for(node_type: str, config: dict[str, Any]):
    _, Performance, _, _ = _import_hierfl()
    if "computeFactor" not in config or config["computeFactor"] is None:
        raise ValueError(f"hierfl_missing_{node_type}_computeFactor")
    compute_factor = float(config["computeFactor"])
    if compute_factor <= 0:
        raise ValueError(f"hierfl_invalid_{node_type}_computeFactor")
    perf_stddev = max(MIN_PERF_STDDEV, compute_factor * 0.1)
    return Performance(compute_factor=compute_factor, performance_stddev=perf_stddev)


def _network_for(node_type: str, config: dict[str, Any]):
    _, _, Network, _ = _import_hierfl()
    if "pingMs" not in config or config["pingMs"] is None:
        raise ValueError(f"hierfl_missing_{node_type}_pingMs")
    if "jitterMs" not in config or config["jitterMs"] is None:
        raise ValueError(f"hierfl_missing_{node_type}_jitterMs")
    if "packetloss" not in config or config["packetloss"] is None:
        raise ValueError(f"hierfl_missing_{node_type}_packetloss")
    if "packetlossStddev" not in config or config["packetlossStddev"] is None:
        raise ValueError(f"hierfl_missing_{node_type}_packetlossStddev")
    if "uploadMbps" not in config or config["uploadMbps"] is None:
        raise ValueError(f"hierfl_missing_{node_type}_uploadMbps")
    if "downloadMbps" not in config or config["downloadMbps"] is None:
        raise ValueError(f"hierfl_missing_{node_type}_downloadMbps")

    latency_avg = int(config["pingMs"])
    latency_stddev = int(config["jitterMs"])
    packet_loss_avg = float(config["packetloss"])
    packet_loss_stddev = float(config["packetlossStddev"])
    upload_speed = float(config["uploadMbps"])
    download_speed = float(config["downloadMbps"])

    if latency_avg < 0 or latency_stddev < 0:
        raise ValueError(f"hierfl_invalid_{node_type}_latency")
    if not (0.0 <= packet_loss_avg <= 1.0) or not (0.0 <= packet_loss_stddev <= 1.0):
        raise ValueError(f"hierfl_invalid_{node_type}_packetloss")
    if upload_speed <= 0 or download_speed <= 0:
        raise ValueError(f"hierfl_invalid_{node_type}_bandwidth")
    return Network(
        latency_avg=latency_avg,
        latency_stddev=latency_stddev,
        packet_loss_avg=packet_loss_avg,
        packet_loss_stddev=packet_loss_stddev,
        upload_speed=upload_speed,
        download_speed=download_speed,
    )


def _node_id(node: Node, config: dict[str, Any], node_type: str) -> str:
    return str(node.id)


def _node_name(node_id: str, config: dict[str, Any]) -> str:
    name = config.get("name")
    return str(name).strip() if name else node_id


def _build_adjacency(edges: list[Edge]) -> dict[int, set[int]]:
    adjacency: dict[int, set[int]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source_node_id, set()).add(edge.target_node_id)
        adjacency.setdefault(edge.target_node_id, set()).add(edge.source_node_id)
    return adjacency


def validate_hierfl_graph(graph: Graph) -> None:
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    adjacency = _build_adjacency(edges)

    super_nodes = [n for n in nodes if n.type == "SuperServerNode"]
    if len(super_nodes) != 1:
        raise ValueError("hierfl_requires_single_superserver")

    server_nodes = [n for n in nodes if n.type == "ServerNode"]
    if not server_nodes:
        raise ValueError("hierfl_requires_server_nodes")

    client_nodes = [n for n in nodes if n.type == "ClientNode"]
    if not client_nodes:
        raise ValueError("hierfl_requires_client_nodes")

    super_id = super_nodes[0].id
    server_ids = {n.id for n in server_nodes}
    for server in server_nodes:
        neighbors = adjacency.get(server.id, set())
        if super_id not in neighbors:
            raise ValueError("hierfl_server_missing_superserver_link")

    for client in client_nodes:
        neighbors = adjacency.get(client.id, set())
        connected_servers = [nid for nid in neighbors if nid in server_ids]
        if len(connected_servers) != 1:
            raise ValueError("hierfl_client_requires_single_server_link")

    required_common = [
        "computeFactor",
        "pingMs",
        "jitterMs",
        "packetloss",
        "packetlossStddev",
        "uploadMbps",
        "downloadMbps",
    ]
    for node in nodes:
        config = _node_config(node)
        for key in required_common:
            if key not in config or config[key] is None:
                raise ValueError(f"hierfl_missing_{node.type}_{key}")


    for client in client_nodes:
        client_config = _node_config(client)
        if "count" not in client_config or client_config["count"] is None:
            raise ValueError("hierfl_missing_ClientNode_count")
        if not client_config.get("type"):
            raise ValueError("hierfl_missing_ClientNode_type")


def _require_training_config(training_config: dict[str, Any] | None) -> dict[str, Any]:
    if training_config is None:
        raise ValueError("hierfl_missing_training_config")
    if "epochs" not in training_config or training_config["epochs"] is None:
        raise ValueError("hierfl_missing_training_epochs")
    if "lr" not in training_config or training_config["lr"] is None:
        raise ValueError("hierfl_missing_training_lr")
    try:
        epochs = int(training_config["epochs"])
    except (TypeError, ValueError):
        raise ValueError("hierfl_invalid_training_epochs")
    try:
        lr = float(training_config["lr"])
    except (TypeError, ValueError):
        raise ValueError("hierfl_invalid_training_lr")
    if epochs < 1:
        raise ValueError("hierfl_invalid_training_epochs")
    if lr <= 0:
        raise ValueError("hierfl_invalid_training_lr")
    return {"epochs": epochs, "lr": lr}


def build_hierfl_simulation(
    graph: Graph,
    training_config: dict[str, Any] | None = None,
    run_time_limit: float | None = None,
):
    HierarchicalSimulation, _, _, _ = _import_hierfl()
    validate_hierfl_graph(graph)

    nodes = list(graph.nodes)
    edges = list(graph.edges)
    adjacency = _build_adjacency(edges)

    super_node = next(n for n in nodes if n.type == "SuperServerNode")
    server_nodes = [n for n in nodes if n.type == "ServerNode"]
    client_nodes = [n for n in nodes if n.type == "ClientNode"]

    super_config = _node_config(super_node)
    super_id = _node_id(super_node, super_config, super_node.type)
    super_name = _node_name(super_id, super_config)
    super_perf = _performance_for(super_node.type, super_config)
    super_net = _network_for(super_node.type, super_config)
    training_config = _require_training_config(training_config)

    limit = DEFAULT_RUN_TIME_LIMIT if run_time_limit is None else float(run_time_limit)
    if limit <= 0:
        raise ValueError("hierfl_invalid_run_time_limit")
    sim = HierarchicalSimulation(run_time_limit=limit)
    sim.set_super_server(
        server_id=super_id,
        name=super_name,
        perf=super_perf,
        net=super_net,
        training_config=training_config,
    )

    server_id_map: dict[int, str] = {}
    used_server_ids: set[str] = set()
    for server in server_nodes:
        config = _node_config(server)
        server_id = _node_id(server, config, server.type)
        if server_id in used_server_ids:
            raise ValueError("hierfl_duplicate_server_id")
        used_server_ids.add(server_id)
        server_id_map[server.id] = server_id

        sim.add_edge_server(
            server_id=server_id,
            name=_node_name(server_id, config),
            perf=_performance_for(server.type, config),
            net=_network_for(server.type, config),
        )

    total_clients = 0
    client_counts: dict[int, int] = {}
    for client in client_nodes:
        config = _node_config(client)
        _node_id(client, config, client.type)
        if "count" not in config or config["count"] is None:
            raise ValueError(f"hierfl_missing_{client.type}_count")
        count = int(config["count"])
        if count < 1:
            raise ValueError("hierfl_client_count_invalid")
        client_counts[client.id] = count
        total_clients += count

    client_index = 0
    server_node_ids = set(server_id_map.keys())
    for client in client_nodes:
        config = _node_config(client)
        neighbors = adjacency.get(client.id, set())
        connected_servers = [nid for nid in neighbors if nid in server_node_ids]
        server_node_id = connected_servers[0]
        server_id = server_id_map[server_node_id]

        base_id = _node_id(client, config, client.type)
        base_name = _node_name(base_id, config)
        count = client_counts[client.id]
        for idx in range(count):
            suffix = f"-{idx + 1}" if count > 1 else ""
            client_id = f"{base_id}{suffix}"
            client_name = f"{base_name}{suffix}" if count > 1 else base_name
            sim.add_client(
                client_id=client_id,
                edge_id=server_id,
                name=client_name,
                perf=_performance_for(client.type, config),
                net=_network_for(client.type, config),
                dataset_partition_id=client_index,
                total_partitions=total_clients,
            )
            client_index += 1

    return sim


def get_hierfl_evaluate_model():
    _, _, _, evaluate_model = _import_hierfl()
    return evaluate_model
