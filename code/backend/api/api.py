from fastapi import APIRouter
from backend.api.routers.graphs import router as graphs_router
from backend.api.routers.nodes import router as nodes_router
from backend.api.routers.edges import router as edges_router
from backend.api.routers.simulation import router as simulation_router

router = APIRouter()

router.include_router(graphs_router)
router.include_router(nodes_router)
router.include_router(edges_router)
router.include_router(simulation_router)