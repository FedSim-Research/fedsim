import json
import uuid
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from backend.db.database import SessionLocal
from backend.db.models import Graph, Node, Edge
from backend.schemas.graph import (
    GraphCreate,
    GraphRename,
    NodeCreate,
    NodeUpdate,
    EdgeCreate,
    EdgeUpdate,
    EdgeConfig,
)


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

        external_id = payload.external_id or str(uuid.uuid4())
        node = Node(
            graph_id=graph_id,
            external_id=external_id,
            type=payload.type,
            config_json=json.dumps(payload.config),
            position_json=json.dumps(payload.position.model_dump()),
        )
        session.add(node)
        session.commit()
        session.refresh(node)
        return node
    finally:
        session.close()


def update_node(node_id: int, payload: NodeUpdate) -> Node | None:
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
        if payload.source_external_id or payload.target_external_id:
            if not payload.source_external_id or not payload.target_external_id:
                raise ValueError("edge_payload_incomplete")
            node_stmt = select(Node).where(
                Node.graph_id == graph_id,
                Node.external_id.in_([payload.source_external_id, payload.target_external_id]),
            )
            nodes = list(session.execute(node_stmt).scalars().all())
            if len(nodes) != 2:
                raise ValueError("node_not_found")
            source_node_id = next(
                node.id for node in nodes if node.external_id == payload.source_external_id
            )
            target_node_id = next(
                node.id for node in nodes if node.external_id == payload.target_external_id
            )

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

        config_model = payload.config or EdgeConfig()
        edge = Edge(
            graph_id=graph_id,
            source_node_id=source_node_id,
            target_node_id=target_node_id,
            config_json=json.dumps(config_model.model_dump()),
        )
        session.add(edge)
        session.commit()
        session.refresh(edge)
        return edge
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


def delete_node(node_id: int) -> bool:
    session = SessionLocal()
    try:
        stmt = select(Node).where(Node.id == node_id)
        node = session.execute(stmt).scalar_one_or_none()
        if node is None:
            return False

        session.execute(
            delete(Edge).where(
                (Edge.source_node_id == node_id) | (Edge.target_node_id == node_id)
            )
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