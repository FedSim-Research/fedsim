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

SERVER_LAYOUT = [
    {
        "key": "hongkong",
        "label": "Hongkong",
        "server_position": {"x": 140.0, "y": 170.0},
        "client_position": {"x": 80.0, "y": 470.0},
        "same_region_latency_ms": 1.41,
    },
    {
        "key": "paris",
        "label": "Paris",
        "server_position": {"x": 430.0, "y": 170.0},
        "client_position": {"x": 370.0, "y": 470.0},
        "same_region_latency_ms": 0.9,
    },
    {
        "key": "sydney",
        "label": "Sydney",
        "server_position": {"x": 720.0, "y": 170.0},
        "client_position": {"x": 660.0, "y": 470.0},
        "same_region_latency_ms": 2.56,
    },
    {
        "key": "california",
        "label": "California",
        "server_position": {"x": 1010.0, "y": 170.0},
        "client_position": {"x": 950.0, "y": 470.0},
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


def ensure_default_graphs() -> None:
    session = SessionLocal()
    try:
        existing = {
            (graph.architecture, graph.name)
            for graph in session.execute(select(Graph)).scalars().all()
        }

        for scenario in SPYKER_PAPER_GRAPHS:
            key = (GRAPH_ARCHITECTURE, scenario["name"])
            if key in existing:
                continue

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
                region_short = region_key[:2]
                server_node_id = f"{scenario['code']}-srv-{region_short}"
                client_node_id = f"{scenario['code']}-cli-{region_short}"
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

        session.commit()
    finally:
        session.close()
