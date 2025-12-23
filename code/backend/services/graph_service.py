import json
import hashlib
from sqlalchemy import select
from backend.db.database import SessionLocal
from backend.db.models import Graph
from backend.schemas.graph import GraphCreate

def normalize_graph(graph: GraphCreate) -> dict:
    """
    Converts a frontend graph into a deterministic from by sorting and normalizing
    """

    sorted_nodes = sort_nodes(graph.nodes)
    normalized_nodes, id_map = assign_node_ids(sorted_nodes)
    normalized_edges = normalize_edges(graph.edges, id_map)

    return {
        "architecture": graph.architecture,
        "nodes": normalized_nodes,
        "edges": normalized_edges,
    }


def sort_nodes(nodes):
    """
    Sort nodes deterministically based on semantic content,
    NOT frontend-generated IDs.
    """
    return sorted(
        nodes,
        key=lambda n: (
            n.data.type,
            sorted(n.data.config.items()),
        ),
    )

def assign_node_ids(nodes):
    """
    Assign deterministic internal IDs (N1, N2, ...) to nodes
    and build a mapping from frontend IDs to internal IDs.
    """

    id_map = {}
    normalized_nodes = []

    for idx, node in enumerate(nodes, start=1):
        internal_id = f"N{idx}"

        id_map[node.id] = internal_id

        normalized_nodes.append(
            {
                "id": internal_id,
                "type": node.data.type,
                "config": node.data.config,
            }
        )

    return normalized_nodes, id_map

def normalize_edges(edges, id_map):
    """
    Remap edges to internal node IDs and sort them deterministically.
    """

    normalized_edges = []

    for edge in edges:
        normalized_edges.append(
            {
                "source": id_map[edge.source],
                "target": id_map[edge.target],
            }
        )

    return sorted(
        normalized_edges,
        key=lambda e: (e["source"], e["target"]),
    )

def hash_graph(normalized_graph: dict) -> str:
    """
    hashes the provided graph into a hex digest
    """
    canonical_json = json.dumps(
        normalized_graph,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical_json.encode("utf-8")).hexdigest()

def save_graph(normalized_graph: dict, graph_hash: str) -> Graph:
    """
    Returns existing graph if hash exists, otherwise persists a new one.
    """

    session = SessionLocal()
    try:
        stmt = select(Graph).where(Graph.graph_hash == graph_hash)
        existing = session.execute(stmt).scalar_one_or_none()

        if existing:
            return existing

        graph = Graph(
            architecture=normalized_graph["architecture"],
            graph_hash=graph_hash,
            nodes_json=json.dumps(normalized_graph["nodes"]),
            edges_json=json.dumps(normalized_graph["edges"]),
        )

        session.add(graph)
        session.commit()
        session.refresh(graph)

        return graph

    finally:
        session.close()