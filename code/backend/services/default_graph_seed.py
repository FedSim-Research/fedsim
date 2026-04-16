from __future__ import annotations

import json
from itertools import combinations

from sqlalchemy import select

from backend.db.database import SessionLocal
from backend.db.models import Edge, Graph, Node

GRAPH_ARCHITECTURE = "spyker"
GRAPH_SOURCE = {
    "paper_title": "Spyker: Asynchronous Multi-Server Federated Learning for Geo-Distributed Clients",
    "doi": "10.1145/3652892.3700778",
}
LAYOUT_VERSION = 3

SERVER_LAYOUT = [
    {
        "key": "hongkong",
        "label": "Hongkong",
        "server_position": {"x": 80.0, "y": 140.0},
        "client_position": {"x": 80.0, "y": 700.0},
        "same_region_latency_ms": 1.41,
    },
    {
        "key": "paris",
        "label": "Paris",
        "server_position": {"x": 640.0, "y": 140.0},
        "client_position": {"x": 640.0, "y": 700.0},
        "same_region_latency_ms": 0.9,
    },
    {
        "key": "sydney",
        "label": "Sydney",
        "server_position": {"x": 1200.0, "y": 140.0},
        "client_position": {"x": 1200.0, "y": 700.0},
        "same_region_latency_ms": 2.56,
    },
    {
        "key": "california",
        "label": "California",
        "server_position": {"x": 1760.0, "y": 140.0},
        "client_position": {"x": 1760.0, "y": 700.0},
        "same_region_latency_ms": 2.14,
    },
]

INTER_SERVER_LATENCY_MS = {
    frozenset({"hongkong", "paris"}): 194.9,
    frozenset({"hongkong", "sydney"}): 132.28,
    frozenset({"hongkong", "california"}): 155.13,
    frozenset({"paris", "sydney"}): 278.83,
    frozenset({"paris", "california"}): 142.25,
    frozenset({"sydney", "california"}): 138.47,
}

DEFAULT_SERVER_CONFIG = {
    "computeFactor": 10.0,
    "performanceSigma": 0.0,
    "uploadMbps": 100.0,
    "downloadMbps": 100.0,
}

DEFAULT_CLIENT_CONFIG = {
    "type": "workstation",
    "computeFactor": 1.0,
    "performanceSigma": 0.0,
    "uploadMbps": 100.0,
    "downloadMbps": 100.0,
}

EDGE_BASE_CONFIG = {
    "jitterMs": 0,
    "packetloss": 0.0,
    "packetlossStddev": 0.0,
}

SPYKER_PAPER_GRAPHS = [
    {
        "code": "s25",
        "seed_key": "spyker-paper-4s-25-25-25-25",
        "name": "Spyker Paper - 4 Servers - 25/25/25/25",
        "counts": {
            "hongkong": 25,
            "paris": 25,
            "sydney": 25,
            "california": 25,
        },
        "notes": [],
    },
    {
        "code": "s52",
        "seed_key": "spyker-paper-4s-52-16-16-16",
        "name": "Spyker Paper - 4 Servers - 52/16/16/16",
        "counts": {
            "hongkong": 52,
            "paris": 16,
            "sydney": 16,
            "california": 16,
        },
        "notes": [],
    },
    {
        "code": "s63",
        "seed_key": "spyker-paper-4s-63-13-12-12",
        "name": "Spyker Paper - 4 Servers - 63/13/12/12",
        "counts": {
            "hongkong": 63,
            "paris": 13,
            "sydney": 12,
            "california": 12,
        },
        "notes": [
            "The paper reports one server with 63 clients and says the remaining clients are divided evenly. "
            "Because 37 cannot be split evenly across three integer client groups, this saved graph keeps the total "
            "at 100 with the closest possible split: 13/12/12.",
        ],
    },
    {
        "code": "s70",
        "seed_key": "spyker-paper-4s-70-10-10-10",
        "name": "Spyker Paper - 4 Servers - 70/10/10/10",
        "counts": {
            "hongkong": 70,
            "paris": 10,
            "sydney": 10,
            "california": 10,
        },
        "notes": [],
    },
]


def _rounded_latency(latency_ms: float) -> int:
    return max(0, int(round(latency_ms)))


def _edge_config(latency_ms: float) -> str:
    return json.dumps(
        {
            "pingMs": _rounded_latency(latency_ms),
            **EDGE_BASE_CONFIG,
        }
    )


def _graph_metadata(scenario: dict[str, object]) -> str:
    counts = scenario["counts"]
    return json.dumps(
        {
            "seed_key": scenario["seed_key"],
            "seed_kind": "default_spyker_paper_graph",
            "layout_version": LAYOUT_VERSION,
            "source": GRAPH_SOURCE,
            "regions": [region["label"] for region in SERVER_LAYOUT],
            "client_distribution": counts,
            "paper_client_training_delay_ms": {
                "distribution": "gaussian",
                "mean": 150,
                "stddev": 7.5,
                "note": "Documented for reference only; the current graph schema does not persist this directly.",
            },
            "paper_bandwidth_mbps": 100,
            "paper_server_latency_ms": {
                "hongkong_hongkong": 1.41,
                "hongkong_paris": 194.9,
                "hongkong_sydney": 132.28,
                "hongkong_california": 155.13,
                "paris_paris": 0.9,
                "paris_sydney": 278.83,
                "paris_california": 142.25,
                "sydney_sydney": 2.56,
                "sydney_california": 138.47,
                "california_california": 2.14,
            },
            "graph_rounding_note": "Edge ping values are rounded to integer milliseconds because the current graph schema stores ping as an integer.",
            "notes": scenario["notes"],
        }
    )


def _graph_layout_needs_refresh(graph: Graph) -> bool:
    if not graph.metadata_json:
        return True

    try:
        metadata = json.loads(graph.metadata_json)
    except json.JSONDecodeError:
        return True

    if not isinstance(metadata, dict):
        return True

    return metadata.get("layout_version") != LAYOUT_VERSION


def _parse_metadata(raw_metadata: str | None) -> dict[str, object]:
    if not raw_metadata:
        return {}

    try:
        metadata = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return {}

    return metadata if isinstance(metadata, dict) else {}


def _node_position(node: Node) -> tuple[float, float]:
    try:
        position = json.loads(node.position_json)
    except json.JSONDecodeError:
        return (0.0, 0.0)

    if not isinstance(position, dict):
        return (0.0, 0.0)

    x = position.get("x", 0.0)
    y = position.get("y", 0.0)
    try:
        return (float(x), float(y))
    except (TypeError, ValueError):
        return (0.0, 0.0)


def _region_node_ids(scenario_code: str, region_key: str) -> tuple[str, str]:
    region_short = region_key[:2]
    return f"{scenario_code}-srv-{region_short}", f"{scenario_code}-cli-{region_short}"


def _apply_graph_layout(graph: Graph, scenario: dict[str, object]) -> None:
    server_nodes = [node for node in graph.nodes if node.type == "ServerNode"]
    client_nodes = {node.id: node for node in graph.nodes if node.type == "ClientNode"}
    clients_by_server_id: dict[str, Node] = {}

    for edge in graph.edges:
        if edge.source_node_id in client_nodes:
            clients_by_server_id[edge.target_node_id] = client_nodes[edge.source_node_id]
        elif edge.target_node_id in client_nodes:
            clients_by_server_id[edge.source_node_id] = client_nodes[edge.target_node_id]

    for index, server_node in enumerate(sorted(server_nodes, key=_node_position)):
        if index >= len(SERVER_LAYOUT):
            break

        region = SERVER_LAYOUT[index]
        server_node.position_json = json.dumps(region["server_position"])

        client_node = clients_by_server_id.get(server_node.id)
        if client_node is not None:
            client_node.position_json = json.dumps(region["client_position"])

    metadata = _parse_metadata(graph.metadata_json)
    if not metadata:
        metadata = json.loads(_graph_metadata(scenario))
    metadata["layout_version"] = LAYOUT_VERSION
    graph.metadata_json = json.dumps(metadata)


def _create_default_graph(session, scenario: dict[str, object]) -> None:
    graph = Graph(
        name=scenario["name"],
        architecture=GRAPH_ARCHITECTURE,
        metadata_json=_graph_metadata(scenario),
    )
    session.add(graph)
    session.flush()

    server_node_ids: dict[str, str] = {}
    client_node_ids: dict[str, str] = {}

    for region in SERVER_LAYOUT:
        region_key = region["key"]
        server_node_id, client_node_id = _region_node_ids(scenario["code"], region_key)
        server_node_ids[region_key] = server_node_id
        client_node_ids[region_key] = client_node_id

        session.add(
            Node(
                id=server_node_id,
                graph_id=graph.id,
                type="ServerNode",
                config_json=json.dumps(
                    {
                        "name": f"{region['label']} Server",
                        **DEFAULT_SERVER_CONFIG,
                    }
                ),
                position_json=json.dumps(region["server_position"]),
            )
        )

        session.add(
            Node(
                id=client_node_id,
                graph_id=graph.id,
                type="ClientNode",
                config_json=json.dumps(
                    {
                        "count": scenario["counts"][region_key],
                        **DEFAULT_CLIENT_CONFIG,
                    }
                ),
                position_json=json.dumps(region["client_position"]),
            )
        )

        session.add(
            Edge(
                graph_id=graph.id,
                source_node_id=server_node_id,
                target_node_id=client_node_id,
                config_json=_edge_config(region["same_region_latency_ms"]),
            )
        )

    for left, right in combinations(SERVER_LAYOUT, 2):
        latency_ms = INTER_SERVER_LATENCY_MS[frozenset({left["key"], right["key"]})]
        session.add(
            Edge(
                graph_id=graph.id,
                source_node_id=server_node_ids[left["key"]],
                target_node_id=server_node_ids[right["key"]],
                config_json=_edge_config(latency_ms),
            )
        )


def ensure_default_graphs() -> None:
    session = SessionLocal()
    try:
        existing_graphs = session.execute(
            select(Graph).where(Graph.architecture == GRAPH_ARCHITECTURE)
        ).scalars().all()
        graphs_by_seed_key: dict[str, Graph] = {}
        graphs_by_name: dict[str, Graph] = {}

        for graph in existing_graphs:
            if graph.name is not None:
                graphs_by_name[graph.name] = graph

            if not graph.metadata_json:
                continue

            metadata = _parse_metadata(graph.metadata_json)
            seed_key = metadata.get("seed_key")
            if isinstance(seed_key, str):
                graphs_by_seed_key[seed_key] = graph

        for scenario in SPYKER_PAPER_GRAPHS:
            graph = graphs_by_seed_key.get(scenario["seed_key"]) or graphs_by_name.get(scenario["name"])
            if graph is None:
                _create_default_graph(session, scenario)
                continue

            if _graph_layout_needs_refresh(graph):
                _apply_graph_layout(graph, scenario)

        session.commit()
    finally:
        session.close()
