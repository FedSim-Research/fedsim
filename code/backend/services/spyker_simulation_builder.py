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
def _import_spyker():
    repo_root = Path(__file__).resolve().parents[3]
    impl_root = repo_root / "code" / "framework" / "impl"
    impl_path = str(impl_root)
    if impl_path not in sys.path:
        sys.path.append(impl_path)

    from main.main_spyker import SpykerSimulation, evaluate_model  # type: ignore
    from simulation.spyker_config import SpykerConfig  # type: ignore
    from specs.performance_metrics import Performance  # type: ignore
    from specs.network_metrics import Network  # type: ignore

    return SpykerSimulation, SpykerConfig, Performance, Network, evaluate_model


def _node_config(node: Node) -> dict[str, Any]:
    if not node.config_json:
        return {}
    try:
        return json.loads(node.config_json)
    except json.JSONDecodeError:
        return {}


def _edge_config(edge: Edge) -> dict[str, Any]:
    if not edge.config_json:
        return {}
    try:
        return json.loads(edge.config_json)
    except json.JSONDecodeError:
        return {}


def _performance_for(node_type: str, config: dict[str, Any]):
    _, _, Performance, _, _ = _import_spyker()
    if "computeFactor" not in config or config["computeFactor"] is None:
        raise ValueError(f"spyker_missing_{node_type}_computeFactor")
    compute_factor = float(config["computeFactor"])
    if compute_factor <= 0:
        raise ValueError(f"spyker_invalid_{node_type}_computeFactor")
    perf_stddev = max(MIN_PERF_STDDEV, compute_factor * 0.1)
    return Performance(compute_factor=compute_factor, performance_stddev=perf_stddev)


def _network_for_edge(edge: Edge):
    _, _, _, Network, _ = _import_spyker()
    config = _edge_config(edge)
    if "pingMs" not in config or config["pingMs"] is None:
        raise ValueError("spyker_missing_edge_pingMs")
    if "jitterMs" not in config or config["jitterMs"] is None:
        raise ValueError("spyker_missing_edge_jitterMs")
    if "packetloss" not in config or config["packetloss"] is None:
        raise ValueError("spyker_missing_edge_packetloss")
    if "packetlossStddev" not in config or config["packetlossStddev"] is None:
        raise ValueError("spyker_missing_edge_packetlossStddev")

    latency_avg = int(config["pingMs"])
    latency_stddev = int(config["jitterMs"])
    packet_loss_avg = float(config["packetloss"])
    packet_loss_stddev = float(config["packetlossStddev"])

    if latency_avg < 0 or latency_stddev < 0:
        raise ValueError("spyker_invalid_edge_latency")
    if not (0.0 <= packet_loss_avg <= 1.0) or not (0.0 <= packet_loss_stddev <= 1.0):
        raise ValueError("spyker_invalid_edge_packetloss")
    return Network(
        latency_avg=latency_avg,
        latency_stddev=latency_stddev,
        packet_loss_avg=packet_loss_avg,
        packet_loss_stddev=packet_loss_stddev,
    )


def _node_id(node: Node) -> str:
    return str(node.id)


def _node_name(node_id: str, config: dict[str, Any]) -> str:
    name = config.get("name")
    return str(name).strip() if name else node_id


def _build_adjacency(edges: list[Edge]) -> dict[str, set[str]]:
    adjacency: dict[str, set[str]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source_node_id, set()).add(edge.target_node_id)
        adjacency.setdefault(edge.target_node_id, set()).add(edge.source_node_id)
    return adjacency


def validate_spyker_graph(graph: Graph) -> None:
    nodes = list(graph.nodes)
    edges = list(graph.edges)
    adjacency = _build_adjacency(edges)

    if any(n.type == "SuperServerNode" for n in nodes):
        raise ValueError("spyker_no_superserver")

    server_nodes = [n for n in nodes if n.type == "ServerNode"]
    if not server_nodes:
        raise ValueError("spyker_requires_server_nodes")

    client_nodes = [n for n in nodes if n.type == "ClientNode"]
    if not client_nodes:
        raise ValueError("spyker_requires_client_nodes")

    server_ids = {n.id for n in server_nodes}
    for client in client_nodes:
        neighbors = adjacency.get(client.id, set())
        connected_servers = [nid for nid in neighbors if nid in server_ids]
        if len(connected_servers) != 1:
            raise ValueError("spyker_client_requires_single_server_link")

    required_common = [
        "computeFactor",
        "uploadMbps",
        "downloadMbps",
    ]
    for node in nodes:
        if node.type == "SuperServerNode":
            continue
        config = _node_config(node)
        for key in required_common:
            if key not in config or config[key] is None:
                raise ValueError(f"spyker_missing_{node.type}_{key}")

    for client in client_nodes:
        client_config = _node_config(client)
        if "count" not in client_config or client_config["count"] is None:
            raise ValueError("spyker_missing_ClientNode_count")

    for edge in edges:
        _network_for_edge(edge)


def build_spyker_simulation(
    graph: Graph,
    run_time_limit: float | None = None,
):
    SpykerSimulation, SpykerConfig, _, _, _ = _import_spyker()
    validate_spyker_graph(graph)

    nodes = list(graph.nodes)
    edges = list(graph.edges)
    adjacency = _build_adjacency(edges)

    server_nodes = [n for n in nodes if n.type == "ServerNode"]
    client_nodes = [n for n in nodes if n.type == "ClientNode"]

    limit = DEFAULT_RUN_TIME_LIMIT if run_time_limit is None else float(run_time_limit)
    if limit <= 0:
        raise ValueError("spyker_invalid_run_time_limit")
    sim = SpykerSimulation(run_time_limit=limit)
    sim.set_spyker_config(SpykerConfig())

    edge_networks: dict[tuple[str, str], Any] = {}
    for edge in edges:
        net = _network_for_edge(edge)
        edge_networks[(edge.source_node_id, edge.target_node_id)] = net
        edge_networks[(edge.target_node_id, edge.source_node_id)] = net

    client_instance_ids: dict[str, list[str]] = {}
    total_clients = 0
    client_counts: dict[str, int] = {}
    for client in client_nodes:
        config = _node_config(client)
        count = int(config.get("count", 1))
        if count < 1:
            raise ValueError("spyker_client_count_invalid")
        client_counts[client.id] = count
        total_clients += count

    for server in server_nodes:
        config = _node_config(server)
        server_id = _node_id(server)
        server_name = _node_name(server_id, config)
        perf = _performance_for(server.type, config)
        upload_speed = float(config["uploadMbps"])
        download_speed = float(config["downloadMbps"])

        neighbors = adjacency.get(server.id, set())
        net: dict[str, Any] = {}
        for neighbor_id in neighbors:
            if (server.id, neighbor_id) in edge_networks:
                net[str(neighbor_id)] = edge_networks[(server.id, neighbor_id)]

        sim.add_server(
            server_id=server_id,
            name=server_name,
            perf=perf,
            net=net,
            download_speed=download_speed,
            upload_speed=upload_speed,
        )

    client_index = 0
    for client in client_nodes:
        client_config = _node_config(client)
        client_upload = float(client_config["uploadMbps"])
        client_download = float(client_config["downloadMbps"])
        perf = _performance_for(client.type, client_config)
        neighbors = adjacency.get(client.id, set())
        server_ids = [nid for nid in neighbors if nid in {n.id for n in server_nodes}]
        server_id = server_ids[0]
        count = client_counts[client.id]

        instance_ids: list[str] = []
        for idx in range(count):
            suffix = f"-{idx + 1}" if count > 1 else ""
            client_id = f"{client.id}{suffix}"
            client_name = _node_name(client_id, client_config)
            sim.add_client(
                client_id=client_id,
                server_id=str(server_id),
                name=client_name,
                perf=perf,
                dataset_partition_id=client_index,
                total_partitions=total_clients,
                download_speed=client_download,
                upload_speed=client_upload,
            )
            instance_ids.append(client_id)
            client_index += 1
        client_instance_ids[client.id] = instance_ids

    for server in server_nodes:
        server_id = server.id
        neighbors = adjacency.get(server_id, set())
        net = {}
        for neighbor_id in neighbors:
            if (server_id, neighbor_id) in edge_networks:
                net[str(neighbor_id)] = edge_networks[(server_id, neighbor_id)]
        for client in client_nodes:
            if client.id in neighbors:
                for instance_id in client_instance_ids.get(client.id, []):
                    net[instance_id] = edge_networks[(server_id, client.id)]
        if net:
            sim.server_registry[str(server_id)].network_metrics = net

    return sim


def get_spyker_evaluate_model():
    _, _, _, _, evaluate_model = _import_spyker()
    return evaluate_model