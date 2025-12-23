from fastapi import APIRouter
from backend.schemas.graph import GraphCreate, GraphResponse
from backend.services import graph_service

router = APIRouter(prefix="/graphs", tags=["graphs"])

@router.post("/", response_model=GraphResponse)
def save_graph(graph: GraphCreate):
    """
    Receives a graph from the frontend, normalizes it and persists it in the db if it has a not existing hash
    """

    normalized_graph = graph_service.normalize_graph(graph)
    hashed_graph = graph_service.hash_graph(normalized_graph)
    db_graph = graph_service.save_graph(
        normalized_graph=normalized_graph,
        graph_hash=hashed_graph,
    )

    return GraphResponse(
        graph_id=db_graph.id,
        architecture=db_graph.architecture,
    )