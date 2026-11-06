from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from fedsim.persistence.models import Edge, Graph, Node

DEFAULT_RUN_TIME_LIMIT = 5000.0
MIN_PERF_STDDEV = 0.01


@lru_cache(maxsize=1)
def _import_spyker():
    from fedsim.engines.spyker.simulation import SpykerSimulation
    from fedsim.evaluation import evaluate_model
    from fedsim.simulation.spyker_config import FullConfiguration
    from fedsim.specs.network_metrics import Network
    from fedsim.specs.performance_metrics import Performance

    return SpykerSimulation, FullConfiguration, Performance, Network, evaluate_model


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


def _require_training_config(training_config: dict[str, Any] | None) -> dict[str, Any]:
    if training_config is None:
        raise ValueError("spyker_missing_training_config")
    if "epochs" not in training_config or training_config["epochs"] is None:
        raise ValueError("spyker_missing_training_epochs")
    if "lr" not in training_config or training_config["lr"] is None:
        raise ValueError("spyker_missing_training_lr")
    try:
        epochs = int(training_config["epochs"])
    except (TypeError, ValueError):
        raise ValueError("spyker_invalid_training_epochs")
    try:
        lr = float(training_config["lr"])
    except (TypeError, ValueError):
        raise ValueError("spyker_invalid_training_lr")
    if epochs < 1:
        raise ValueError("spyker_invalid_training_epochs")
    if lr <= 0:
        raise ValueError("spyker_invalid_training_lr")
    result = {"local_epochs": epochs, "learning_rate": lr}
    if "batch_size" in training_config and training_config["batch_size"] is not None:
        try:
            batch_size = int(training_config["batch_size"])
        except (TypeError, ValueError):
            raise ValueError("spyker_invalid_batch_size")
        if batch_size < 1:
            raise ValueError("spyker_invalid_batch_size")
        result["batch_size"] = batch_size
    if "model_complexity" in training_config and training_config["model_complexity"] is not None:
        try:
            model_complexity = float(training_config["model_complexity"])
        except (TypeError, ValueError):
            raise ValueError("spyker_invalid_model_complexity")
        if model_complexity <= 0:
            raise ValueError("spyker_invalid_model_complexity")
        result["model_complexity"] = model_complexity
    # TODO: Implement client and server strategy selection here from frontend parse
    return result


def _require_spyker_config(spyker_config: dict[str, Any] | None) -> dict[str, Any]:
    if not spyker_config:
        return {}
    result: dict[str, Any] = {}
    float_positive = {"min_learning_rate", "sigmoid_phi", "server_learning_rate"}
    float_non_negative = {"decay_beta", "tcp_rto_delay"}
    int_min_one = {"h_inter", "h_intra"}

    for key, value in spyker_config.items():
        if value is None:
            continue
        if key in float_positive:
            val = float(value)
            if val <= 0:
                raise ValueError(f"spyker_invalid_{key}")
            result[key] = val
        elif key in float_non_negative:
            val = float(value)
            if val < 0:
                raise ValueError(f"spyker_invalid_{key}")
            result[key] = val
        elif key in int_min_one:
            val = int(value)
            if val < 1:
                raise ValueError(f"spyker_invalid_{key}")
            result[key] = val
    return result


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
):
    SpykerSimulation, _, _, _, _ = _import_spyker()
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
    sim = SpykerSimulation(dataset_id=dataset_id or "uoft-cs/cifar10", gpu_budget=gpu_budget)
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
    _, _, _, _, evaluate_model = _import_spyker()
    return evaluate_model
