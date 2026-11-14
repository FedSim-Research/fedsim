from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fedsim.persistence.models import Edge, Graph, Node
from fedsim.services.input_values import (
    parse_nonnegative_float,
    parse_positive_float,
    parse_positive_int,
    parse_training_config,
)
from fedsim.services.node_performance import parse_node_performance

DEFAULT_RUN_TIME_LIMIT = 5000.0


@lru_cache(maxsize=1)
def _import_hierfl():
    from fedsim.engines.hierarchical.simulation import HierarchicalSimulation
    from fedsim.evaluation import evaluate_model
    from fedsim.specs.network_metrics import Network

    return HierarchicalSimulation, Network, evaluate_model


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
    return parse_node_performance(node_type, config, prefix="hierfl")


def _network_for_edge(edge: Edge):
    _, Network, _ = _import_hierfl()
    config = _edge_config(edge)
    if "pingMs" not in config or config["pingMs"] is None:
        raise ValueError("hierfl_missing_edge_pingMs")
    if "jitterMs" not in config or config["jitterMs"] is None:
        raise ValueError("hierfl_missing_edge_jitterMs")
    if "packetloss" not in config or config["packetloss"] is None:
        raise ValueError("hierfl_missing_edge_packetloss")
    if "packetlossStddev" not in config or config["packetlossStddev"] is None:
        raise ValueError("hierfl_missing_edge_packetlossStddev")

    latency_avg = parse_nonnegative_float(config["pingMs"], "hierfl_invalid_edge_latency")
    latency_stddev = parse_nonnegative_float(config["jitterMs"], "hierfl_invalid_edge_latency")
    packet_loss_avg = parse_nonnegative_float(
        config["packetloss"], "hierfl_invalid_edge_packetloss"
    )
    packet_loss_stddev = parse_nonnegative_float(
        config["packetlossStddev"], "hierfl_invalid_edge_packetloss"
    )

    if latency_avg < 0 or latency_stddev < 0:
        raise ValueError("hierfl_invalid_edge_latency")
    if not (0.0 <= packet_loss_avg <= 1.0) or not (0.0 <= packet_loss_stddev <= 1.0):
        raise ValueError("hierfl_invalid_edge_packetloss")
    return Network(
        latency_avg=latency_avg,
        latency_stddev=latency_stddev,
        packet_loss_avg=packet_loss_avg,
        packet_loss_stddev=packet_loss_stddev,
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
        "uploadMbps",
        "downloadMbps",
    ]
    for node in nodes:
        config = _node_config(node)
        for key in required_common:
            if key not in config or config[key] is None:
                raise ValueError(f"hierfl_missing_{node.type}_{key}")
        _performance_for(node.type, config)
        for field in ["uploadMbps", "downloadMbps"]:
            parse_positive_float(config[field], f"hierfl_invalid_{node.type}_{field}")

    for client in client_nodes:
        client_config = _node_config(client)
        if "count" not in client_config or client_config["count"] is None:
            raise ValueError("hierfl_missing_ClientNode_count")
        parse_positive_int(client_config["count"], "hierfl_client_count_invalid")
        if not client_config.get("type"):
            raise ValueError("hierfl_missing_ClientNode_type")

    for edge in edges:
        _network_for_edge(edge)


def _require_training_config(training_config: dict[str, Any] | None) -> dict[str, Any]:
    return parse_training_config(training_config, prefix="hierfl")


def build_hierfl_simulation(
    graph: Graph,
    training_config: dict[str, Any] | None = None,
    run_time_limit: float | None = None,
    gpu_budget: float | None = None,
    dataset_id: str | None = None,
    seed: int | None = None,
    run_id: str | None = None,
    graph_id: int | None = None,
    eval_interval: float | None = None,
):
    HierarchicalSimulation, Network, _ = _import_hierfl()
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
    super_upload = float(super_config["uploadMbps"])
    super_download = float(super_config["downloadMbps"])
    training_config = _require_training_config(training_config)

    limit = DEFAULT_RUN_TIME_LIMIT if run_time_limit is None else float(run_time_limit)
    if limit <= 0:
        raise ValueError("hierfl_invalid_run_time_limit")
    if eval_interval is not None and float(eval_interval) < 0:
        raise ValueError("hierfl_invalid_eval_interval")
    sim = HierarchicalSimulation(
        dataset_id=dataset_id or "uoft-cs/cifar10",
        run_time_limit=limit,
        gpu_budget=gpu_budget,
        seed=seed,
    )
    sim.set_metadata(
        run_id=run_id or "unknown_run",
        graph_id=str(graph.id if graph_id is None else graph_id),
        eval_interval=eval_interval,
    )
    sim.set_super_server(
        server_id=super_id,
        name=super_name,
        perf=super_perf,
        upload_speed=super_upload,
        download_speed=super_download,
        training_config=training_config,
    )

    edge_networks: dict[tuple[int, int], Network] = {}
    for edge in edges:
        net = _network_for_edge(edge)
        edge_networks[(edge.source_node_id, edge.target_node_id)] = net
        edge_networks[(edge.target_node_id, edge.source_node_id)] = net

    server_id_map: dict[int, str] = {}
    used_server_ids: set[str] = set()
    for server in server_nodes:
        config = _node_config(server)
        server_id = _node_id(server, config, server.type)
        if server_id in used_server_ids:
            raise ValueError("hierfl_duplicate_server_id")
        used_server_ids.add(server_id)
        server_id_map[server.id] = server_id

        server_upload = float(config["uploadMbps"])
        server_download = float(config["downloadMbps"])

        network_dict: dict[str, Network] = {}
        server_neighbors = adjacency.get(server.id, set())
        if super_node.id in server_neighbors:
            net = edge_networks.get((server.id, super_node.id))
            if net is None:
                raise ValueError("hierfl_missing_edge_network")
            network_dict[super_id] = net

        sim.add_edge_server(
            server_id=server_id,
            name=_node_name(server_id, config),
            perf=_performance_for(server.type, config),
            net=network_dict,
            upload_speed=server_upload,
            download_speed=server_download,
        )

    total_clients = 0
    client_counts: dict[int, int] = {}
    client_bandwidths: dict[int, tuple[float, float]] = {}
    for client in client_nodes:
        config = _node_config(client)
        _node_id(client, config, client.type)
        if "count" not in config or config["count"] is None:
            raise ValueError(f"hierfl_missing_{client.type}_count")
        count = int(config["count"])
        if count < 1:
            raise ValueError("hierfl_client_count_invalid")
        client_counts[client.id] = count
        client_bandwidths[client.id] = (
            float(config["uploadMbps"]),
            float(config["downloadMbps"]),
        )
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
        client_upload, client_download = client_bandwidths[client.id]

        edge_net = edge_networks.get((server_node_id, client.id))
        if edge_net is None:
            raise ValueError("hierfl_missing_edge_network")

        for idx in range(count):
            suffix = f"-{idx + 1}" if count > 1 else ""
            client_id = f"{base_id}{suffix}"
            client_name = f"{base_name}{suffix}" if count > 1 else base_name
            network_dict = sim.server_registry[server_id].network_metrics or {}
            network_dict[client_id] = edge_net
            sim.server_registry[server_id].network_metrics = network_dict
            add_client_kwargs = {
                "client_id": client_id,
                "edge_id": server_id,
                "name": client_name,
                "perf": _performance_for(client.type, config),
                "upload_speed": client_upload,
                "download_speed": client_download,
                "dataset_partition_id": client_index,
                "total_partitions": total_clients,
                "seed": None if seed is None else seed + client_index,
            }
            sim.add_client(**add_client_kwargs)
            client_index += 1

    return sim


def get_hierfl_evaluate_model():
    _, _, evaluate_model = _import_hierfl()
    return evaluate_model
