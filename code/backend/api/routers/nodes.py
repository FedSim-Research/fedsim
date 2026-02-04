import json
from fastapi import APIRouter, HTTPException
from backend.schemas.graph import NodeUpdate, NodeResponse
from backend.services import graph_service

router = APIRouter(prefix="/nodes", tags=["nodes"])


@router.put("/{node_id}", response_model=NodeResponse)
def update_node(node_id: str, payload: NodeUpdate):
    node = graph_service.update_node(node_id, payload)
    if node is None:
        raise HTTPException(status_code=404, detail="Node not found")

    return NodeResponse(
        node_id=node.id,
        graph_id=node.graph_id,
        type=node.type,
        config=json.loads(node.config_json),
        position=json.loads(node.position_json),
    )


@router.delete("/{node_id}")
def delete_node(node_id: str):
    deleted = graph_service.delete_node(node_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Node not found")

    return {"status": "deleted"}
