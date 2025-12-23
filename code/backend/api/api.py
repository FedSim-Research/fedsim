from fastapi import APIRouter
from backend.api.routers.graphs import router as graphs_router
from backend.api.routers.simulation import router as simulation_router

router = APIRouter()

router.include_router(graphs_router)
router.include_router(simulation_router)