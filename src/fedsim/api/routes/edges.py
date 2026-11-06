import json

from fastapi import APIRouter, HTTPException

from fedsim.api.schemas import EdgeResponse, EdgeUpdate
from fedsim.services import graph_service

router = APIRouter(prefix="/edges", tags=["edges"])


@router.delete("/{edge_id}")
def delete_edge(edge_id: int):
    deleted = graph_service.delete_edge(edge_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")

    return {"status": "deleted"}


@router.put("/{edge_id}", response_model=EdgeResponse)
def update_edge(edge_id: int, payload: EdgeUpdate):
    edge = graph_service.update_edge(edge_id, payload)
    if edge is None:
        raise HTTPException(status_code=404, detail="Edge not found")
    return EdgeResponse(
        edge_id=edge.id,
        graph_id=edge.graph_id,
        source_node_id=edge.source_node_id,
        target_node_id=edge.target_node_id,
        config=json.loads(edge.config_json) if edge.config_json else None,
    )
