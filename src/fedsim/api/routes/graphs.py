import json

from fastapi import APIRouter, HTTPException
from sqlalchemy.exc import IntegrityError

from fedsim.api.schemas import (
    EdgeCreate,
    EdgeResponse,
    GraphCreate,
    GraphDetail,
    GraphMetadataPatch,
    GraphRename,
    GraphResponse,
    NodeCreate,
    NodeResponse,
    VflowGraph,
)
from fedsim.services import graph_service

router = APIRouter(prefix="/graphs", tags=["graphs"])


def _node_to_response(node) -> NodeResponse:
    return NodeResponse(
        node_id=node.id,
        graph_id=node.graph_id,
        type=node.type,
        config=json.loads(node.config_json),
        position=json.loads(node.position_json),
    )


def _edge_to_response(edge) -> EdgeResponse:
    return EdgeResponse(
        edge_id=edge.id,
        graph_id=edge.graph_id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        config=json.loads(edge.config_json) if edge.config_json else None,
    )


@router.post("/", response_model=GraphResponse)
def save_graph(payload: GraphCreate):
    db_graph = graph_service.create_graph(payload)
    return GraphResponse(
        graph_id=db_graph.id,
        name=db_graph.name,
        architecture=db_graph.architecture,
        metadata=json.loads(db_graph.metadata_json) if db_graph.metadata_json else None,
    )


@router.get("/", response_model=list[GraphResponse])
def list_graphs():
    graphs = graph_service.list_graphs()
    return [
        GraphResponse(
            graph_id=graph.id,
            name=graph.name,
            architecture=graph.architecture,
            metadata=json.loads(graph.metadata_json) if graph.metadata_json else None,
        )
        for graph in graphs
    ]


@router.get("/{graph_id}", response_model=GraphDetail)
def get_graph(graph_id: int):
    graph = graph_service.get_graph(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    return GraphDetail(
        graph_id=graph.id,
        name=graph.name,
        architecture=graph.architecture,
        metadata=json.loads(graph.metadata_json) if graph.metadata_json else None,
        nodes=[_node_to_response(node) for node in graph.nodes],
        edges=[_edge_to_response(edge) for edge in graph.edges],
    )


@router.put("/{graph_id}/name", response_model=GraphResponse)
def rename_graph(graph_id: int, payload: GraphRename):
    graph = graph_service.rename_graph(graph_id, payload)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    return GraphResponse(
        graph_id=graph.id,
        name=graph.name,
        architecture=graph.architecture,
        metadata=json.loads(graph.metadata_json) if graph.metadata_json else None,
    )


@router.patch("/{graph_id}/metadata", response_model=GraphResponse)
def patch_graph_metadata(graph_id: int, payload: GraphMetadataPatch):
    graph = graph_service.patch_graph_metadata(graph_id, payload.patch)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    return GraphResponse(
        graph_id=graph.id,
        name=graph.name,
        architecture=graph.architecture,
        metadata=json.loads(graph.metadata_json) if graph.metadata_json else None,
    )


@router.get("/{graph_id}/vflow", response_model=VflowGraph)
def get_graph_vflow(graph_id: int):
    graph = graph_service.get_graph(graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    node_by_id = {node.id: node for node in graph.nodes}
    nodes = []
    for node in graph.nodes:
        nodes.append(
            {
                "id": node.id,
                "point": json.loads(node.position_json),
                "type": node.type,
                "data": {
                    "type": node.type,
                    "config": json.loads(node.config_json),
                    "environment": graph.architecture,
                    "fromJson": True,
                    "selected": False,
                },
            }
        )

    edges = []
    for edge in graph.edges:
        source_node = node_by_id.get(edge.source_node_id)
        target_node = node_by_id.get(edge.target_node_id)
        if source_node is None or target_node is None:
            continue
        edges.append(
            {
                "id": str(edge.id),
                "source": source_node.id,
                "target": target_node.id,
                "config": json.loads(edge.config_json) if edge.config_json else None,
                "sourceHandle": None,
                "targetHandle": None,
                "reconnectable": True,
                "floating": False,
            }
        )

    return VflowGraph(nodes=nodes, edges=edges)


@router.delete("/{graph_id}")
def delete_graph(graph_id: int):
    deleted = graph_service.delete_graph(graph_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Graph not found")

    return {"status": "deleted"}


@router.put("/{graph_id}/state", response_model=GraphDetail)
def replace_graph_state(graph_id: int, payload: VflowGraph):
    try:
        graph = graph_service.replace_graph_state(graph_id, payload)
    except ValueError as exc:
        if str(exc) == "edge_payload_incomplete":
            raise HTTPException(status_code=400, detail="Edge references missing nodes")
        if str(exc) == "duplicate_node_id":
            raise HTTPException(status_code=400, detail="Node IDs must be unique within a graph")
        if str(exc) == "node_graph_mismatch":
            raise HTTPException(
                status_code=409, detail="Node IDs are already used by another graph"
            )
        raise
    except IntegrityError as exc:
        # A concurrent writer can invalidate the identity check before commit.
        raise HTTPException(
            status_code=409, detail="Graph state conflicts with another update"
        ) from exc
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    return GraphDetail(
        graph_id=graph.id,
        name=graph.name,
        architecture=graph.architecture,
        metadata=json.loads(graph.metadata_json) if graph.metadata_json else None,
        nodes=[_node_to_response(node) for node in graph.nodes],
        edges=[_edge_to_response(edge) for edge in graph.edges],
    )


@router.post("/{graph_id}/nodes", response_model=NodeResponse)
def create_node(graph_id: int, payload: NodeCreate):
    try:
        node = graph_service.create_node(graph_id, payload)
    except ValueError as exc:
        if str(exc) == "graph_not_found":
            raise HTTPException(status_code=404, detail="Graph not found")
        raise

    return _node_to_response(node)


@router.post("/{graph_id}/edges", response_model=EdgeResponse)
def create_edge(graph_id: int, payload: EdgeCreate):
    try:
        edge = graph_service.create_edge(graph_id, payload)
    except ValueError as exc:
        if str(exc) == "graph_not_found":
            raise HTTPException(status_code=404, detail="Graph not found")
        if str(exc) == "node_not_found":
            raise HTTPException(status_code=404, detail="Source or target node not found")
        if str(exc) == "node_graph_mismatch":
            raise HTTPException(status_code=400, detail="Nodes do not belong to graph")
        if str(exc) == "edge_payload_incomplete":
            raise HTTPException(
                status_code=400,
                detail="Provide node IDs for both source and target",
            )
        if str(exc) == "edge_exists":
            raise HTTPException(status_code=409, detail="Edge already exists")
        raise

    return _edge_to_response(edge)
