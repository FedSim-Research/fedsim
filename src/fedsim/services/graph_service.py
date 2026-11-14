import json
import uuid

from sqlalchemy import delete, select
from sqlalchemy.orm import selectinload

from fedsim.api.schemas import (
    EdgeCreate,
    EdgeUpdate,
    GraphCreate,
    GraphRename,
    NodeCreate,
    NodeUpdate,
    VflowGraph,
)
from fedsim.persistence.database import SessionLocal
from fedsim.persistence.models import Edge, Graph, Node


def create_graph(payload: GraphCreate) -> Graph:
    session = SessionLocal()
    try:
        graph = Graph(
            name=payload.name,
            architecture=payload.architecture,
            metadata_json=json.dumps(payload.metadata) if payload.metadata is not None else None,
        )
        session.add(graph)
        session.commit()
        session.refresh(graph)
        return graph
    finally:
        session.close()


def delete_graph(graph_id: int) -> bool:
    session = SessionLocal()
    try:
        stmt = select(Graph).where(Graph.id == graph_id)
        graph = session.execute(stmt).scalar_one_or_none()
        if graph is None:
            return False

        session.delete(graph)
        session.commit()
        return True
    finally:
        session.close()


def rename_graph(graph_id: int, payload: GraphRename) -> Graph | None:
    session = SessionLocal()
    try:
        stmt = select(Graph).where(Graph.id == graph_id)
        graph = session.execute(stmt).scalar_one_or_none()
        if graph is None:
            return None

        graph.name = payload.name
        session.commit()
        session.refresh(graph)
        return graph
    finally:
        session.close()


def patch_graph_metadata(graph_id: int, patch: dict) -> Graph | None:
    session = SessionLocal()
    try:
        stmt = select(Graph).where(Graph.id == graph_id)
        graph = session.execute(stmt).scalar_one_or_none()
        if graph is None:
            return None

        current_metadata = {}
        if graph.metadata_json:
            try:
                parsed = json.loads(graph.metadata_json)
                if isinstance(parsed, dict):
                    current_metadata = parsed
            except json.JSONDecodeError:
                current_metadata = {}

        merged = dict(current_metadata)
        for key, value in patch.items():
            if value is None:
                merged.pop(key, None)
            else:
                merged[key] = value

        graph.metadata_json = json.dumps(merged) if merged else None
        session.commit()
        session.refresh(graph)
        return graph
    finally:
        session.close()


def list_graphs() -> list[Graph]:
    session = SessionLocal()
    try:
        stmt = select(Graph).order_by(Graph.id.desc())
        return list(session.execute(stmt).scalars().all())
    finally:
        session.close()


def get_graph(graph_id: int) -> Graph | None:
    session = SessionLocal()
    try:
        stmt = (
            select(Graph)
            .where(Graph.id == graph_id)
            .options(
                selectinload(Graph.nodes),
                selectinload(Graph.edges),
            )
        )
        return session.execute(stmt).scalar_one_or_none()
    finally:
        session.close()


def create_node(graph_id: int, payload: NodeCreate) -> Node:
    session = SessionLocal()
    try:
        stmt = select(Graph).where(Graph.id == graph_id)
        graph = session.execute(stmt).scalar_one_or_none()
        if graph is None:
            raise ValueError("graph_not_found")

        node_id = str(uuid.uuid4())
        config = dict(payload.config)
        node = Node(
            id=node_id,
            graph_id=graph_id,
            type=payload.type,
            config_json=json.dumps(config),
            position_json=json.dumps(payload.position.model_dump()),
        )
        session.add(node)
        session.commit()
        session.refresh(node)
        return node
    finally:
        session.close()


def update_node(node_id: str, payload: NodeUpdate) -> Node | None:
    session = SessionLocal()
    try:
        stmt = select(Node).where(Node.id == node_id)
        node = session.execute(stmt).scalar_one_or_none()
        if node is None:
            return None

        if payload.type is not None:
            node.type = payload.type
        if payload.config is not None:
            node.config_json = json.dumps(payload.config)
        if payload.position is not None:
            node.position_json = json.dumps(payload.position.model_dump())

        session.commit()
        session.refresh(node)
        return node
    finally:
        session.close()


def create_edge(graph_id: int, payload: EdgeCreate) -> Edge:
    session = SessionLocal()
    try:
        graph_stmt = select(Graph).where(Graph.id == graph_id)
        graph = session.execute(graph_stmt).scalar_one_or_none()
        if graph is None:
            raise ValueError("graph_not_found")

        source_node_id = payload.source_node_id
        target_node_id = payload.target_node_id

        if source_node_id is None or target_node_id is None:
            raise ValueError("edge_payload_incomplete")

        node_stmt = select(Node).where(Node.id.in_([source_node_id, target_node_id]))
        nodes = list(session.execute(node_stmt).scalars().all())
        if len(nodes) != 2:
            raise ValueError("node_not_found")

        node_graph_ids = {node.graph_id for node in nodes}
        if node_graph_ids != {graph_id}:
            raise ValueError("node_graph_mismatch")

        existing_stmt = select(Edge).where(
            Edge.graph_id == graph_id,
            Edge.source_node_id == source_node_id,
            Edge.target_node_id == target_node_id,
        )
        if session.execute(existing_stmt).scalar_one_or_none() is not None:
            raise ValueError("edge_exists")

        config = payload.config.model_dump() if payload.config else {}
        edge = Edge(
            graph_id=graph_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            config_json=json.dumps(config),
        )
        session.add(edge)
        session.commit()
        session.refresh(edge)
        return edge
    finally:
        session.close()


def delete_node(node_id: str) -> bool:
    session = SessionLocal()
    try:
        stmt = select(Node).where(Node.id == node_id)
        node = session.execute(stmt).scalar_one_or_none()
        if node is None:
            return False

        session.execute(
            delete(Edge).where((Edge.source_node_id == node_id) | (Edge.target_node_id == node_id))
        )
        session.delete(node)
        session.commit()
        return True
    finally:
        session.close()


def delete_edge(edge_id: int) -> bool:
    session = SessionLocal()
    try:
        stmt = select(Edge).where(Edge.id == edge_id)
        edge = session.execute(stmt).scalar_one_or_none()
        if edge is None:
            return False

        session.delete(edge)
        session.commit()
        return True
    finally:
        session.close()


def update_edge(edge_id: int, payload: EdgeUpdate) -> Edge | None:
    session = SessionLocal()
    try:
        stmt = select(Edge).where(Edge.id == edge_id)
        edge = session.execute(stmt).scalar_one_or_none()
        if edge is None:
            return None
        edge.config_json = json.dumps(payload.config.model_dump())
        session.commit()
        session.refresh(edge)
        return edge
    finally:
        session.close()


def replace_graph_state(graph_id: int, payload: VflowGraph) -> Graph | None:
    session = SessionLocal()
    try:
        stmt = select(Graph).where(Graph.id == graph_id)
        graph = session.execute(stmt).scalar_one_or_none()
        if graph is None:
            return None

        requested_ids = [node.id for node in payload.nodes]
        if len(set(requested_ids)) != len(requested_ids):
            raise ValueError("duplicate_node_id")
        conflicting_node = session.execute(
            select(Node.id).where(Node.id.in_(requested_ids), Node.graph_id != graph_id).limit(1)
        ).first()
        if conflicting_node is not None:
            raise ValueError("node_graph_mismatch")

        session.execute(delete(Edge).where(Edge.graph_id == graph_id))
        session.execute(delete(Node).where(Node.graph_id == graph_id))

        node_ids: set[str] = set()
        for node in payload.nodes:
            node_type = node.data.type or node.type
            node_ids.add(node.id)
            session.add(
                Node(
                    id=node.id,
                    graph_id=graph_id,
                    type=node_type,
                    config_json=json.dumps(node.data.config),
                    position_json=json.dumps(node.point.model_dump()),
                )
            )

        for edge in payload.edges:
            if edge.source not in node_ids or edge.target not in node_ids:
                raise ValueError("edge_payload_incomplete")
            config_json = json.dumps(edge.config.model_dump()) if edge.config else None
            session.add(
                Edge(
                    graph_id=graph_id,
                    source_node_id=edge.source,
                    target_node_id=edge.target,
                    config_json=config_json,
                )
            )

        session.commit()
        refreshed = session.execute(
            select(Graph)
            .where(Graph.id == graph_id)
            .options(selectinload(Graph.nodes), selectinload(Graph.edges))
        ).scalar_one_or_none()
        return refreshed
    finally:
        session.close()
