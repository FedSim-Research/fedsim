from fastapi import APIRouter, HTTPException
from backend.services import graph_service

router = APIRouter(prefix="/edges", tags=["edges"])


@router.delete("/{edge_id}")
def delete_edge(edge_id: int):
    deleted = graph_service.delete_edge(edge_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Edge not found")

    return {"status": "deleted"}