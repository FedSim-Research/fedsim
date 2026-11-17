from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fedsim.persistence.models import Edge, Graph, Node
from fedsim.services.input_values import (
    SPYKER_MODE_CHOICES,
    parse_bool,
    parse_choice,
    parse_h_inter,
    parse_nonnegative_float,
    parse_positive_float,
    parse_positive_int,
    parse_training_config,
)
from fedsim.services.node_performance import parse_node_performance

DEFAULT_RUN_TIME_LIMIT = 5000.0


@lru_cache(maxsize=1)
def _import_spyker():
    from fedsim.engines.spyker.simulation import SpykerSimulation
    from fedsim.evaluation import evaluate_models
    from fedsim.specs.network_metrics import Network

    return SpykerSimulation, Network, evaluate_models


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
    return parse_node_performance(node_type, config, prefix="spyker")


def _network_for_edge(edge: Edge):
    _, Network, _ = _import_spyker()
    config = _edge_config(edge)
    if "pingMs" not in config or config["pingMs"] is None:
        raise ValueError("spyker_missing_edge_pingMs")
    if "jitterMs" not in config or config["jitterMs"] is None:
        raise ValueError("spyker_missing_edge_jitterMs")
    if "packetloss" not in config or config["packetloss"] is None:
        raise ValueError("spyker_missing_edge_packetloss")
    if "packetlossStddev" not in config or config["packetlossStddev"] is None:
        raise ValueError("spyker_missing_edge_packetlossStddev")

    latency_avg = parse_nonnegative_float(config["pingMs"], "spyker_invalid_edge_latency")
    latency_stddev = parse_nonnegative_float(config["jitterMs"], "spyker_invalid_edge_latency")
    packet_loss_avg = parse_nonnegative_float(
        config["packetloss"], "spyker_invalid_edge_packetloss"
    )
    packet_loss_stddev = parse_nonnegative_float(
        config["packetlossStddev"], "spyker_invalid_edge_packetloss"
    )

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
    for server in server_nodes:
        if not (server_ids - {server.id}).issubset(adjacency.get(server.id, set())):
            raise ValueError("spyker_requires_fully_connected_servers")

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
        _performance_for(node.type, config)
        for field in ["uploadMbps", "downloadMbps"]:
            parse_positive_float(config[field], f"spyker_invalid_{node.type}_{field}")

    for client in client_nodes:
        client_config = _node_config(client)
        if "count" not in client_config or client_config["count"] is None:
            raise ValueError("spyker_missing_ClientNode_count")
        parse_positive_int(client_config["count"], "spyker_client_count_invalid")

    for edge in edges:
        _network_for_edge(edge)


def _require_training_config(training_config: dict[str, Any] | None) -> dict[str, Any]:
    parsed = parse_training_config(training_config, prefix="spyker")
    return {"local_epochs": parsed.pop("epochs"), "learning_rate": parsed.pop("lr"), **parsed}


def _require_spyker_config(spyker_config: dict[str, Any] | None) -> dict[str, Any]:
    if not spyker_config:
        return {}
    parsers = {
        "min_learning_rate": parse_positive_float,
        "sigmoid_phi": parse_positive_float,
        "server_learning_rate": parse_positive_float,
        "decay_beta": parse_nonnegative_float,
        "tcp_rto_delay": parse_nonnegative_float,
        "sample_weighting": parse_bool,
        "aggregation_delay": parse_bool,
        "age_announcements": parse_bool,
        "fifo_links": parse_bool,
        "sync_timeout": parse_positive_float,
        "h_inter": parse_h_inter,
        "h_intra": parse_positive_int,
    }
    for key, choices in SPYKER_MODE_CHOICES.items():
        parsers[key] = lambda value, code, choices=choices: parse_choice(value, choices, code)
    return {
        key: parsers[key](value, f"spyker_invalid_{key}")
        for key, value in spyker_config.items()
        if value is not None and key in parsers
    }


def build_spyker_simulation(
    graph: Graph,
    training_config: dict[str, Any] | None = None,
    spyker_config: dict[str, Any] | None = None,
    run_time_limit: float | None = None,
    # eval_time_delay: float | None = None,  TODO: Uncomment and inject in simulation_config
    idle_token_delay: float | None = None,
    gpu_budget: float | None = None,
    dataset_id: str | None = None,
    seed: int | None = None,
    run_id: str | None = None,
    graph_id: int | None = None,
    eval_interval: float | None = None,
    partitioning: str | None = None,
    labels_per_client: int | None = None,
    local_holdout: float | None = None,
):
    SpykerSimulation, _, _ = _import_spyker()
    validate_spyker_graph(graph)

    nodes = list(graph.nodes)
    edges = list(graph.edges)
    adjacency = _build_adjacency(edges)

    server_nodes = [n for n in nodes if n.type == "ServerNode"]
    client_nodes = [n for n in nodes if n.type == "ClientNode"]

    limit = DEFAULT_RUN_TIME_LIMIT if run_time_limit is None else float(run_time_limit)
    if limit <= 0:
        raise ValueError("spyker_invalid_run_time_limit")
    spyker_training_config = _require_training_config(training_config)
    algorithm_config = _require_spyker_config(spyker_config)
    if eval_interval is not None and float(eval_interval) < 0:
        raise ValueError("spyker_invalid_eval_interval")
    simulation_config: dict[str, Any] = {
        "run_time_limit": limit,
        "eval_time_delay": 500.0 if eval_interval is None else float(eval_interval),
    }
    if idle_token_delay is not None:
        idle = float(idle_token_delay)
        if idle < 0:
            raise ValueError("spyker_invalid_idle_token_delay")
        simulation_config["idle_token_delay"] = idle
    sim = SpykerSimulation(
        dataset_id=dataset_id or "uoft-cs/cifar10",
        gpu_budget=gpu_budget,
        seed=seed,
        partitioning=partitioning or "iid",
        labels_per_client=labels_per_client,
        **({} if local_holdout is None else {"local_holdout": local_holdout}),
    )
    sim.set_configurations(
        spyker_params=algorithm_config,
        training_params=spyker_training_config,
        simulation_params=simulation_config,
    )

    sim.set_metadata(
        run_id=run_id or "unknown_run",
        graph_id=str(graph.id if graph_id is None else graph_id),
        eval_interval=eval_interval,
    )

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
            add_client_kwargs = {
                "client_id": client_id,
                "server_id": str(server_id),
                "name": client_name,
                "perf": perf,
                "dataset_partition_id": client_index,
                "total_partitions": total_clients,
                "download_speed": client_download,
                "upload_speed": client_upload,
                "seed": None if seed is None else seed + client_index,
            }
            sim.add_client(**add_client_kwargs)
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
    _, _, evaluate_model = _import_spyker()
    return evaluate_model
