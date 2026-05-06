from fastapi import APIRouter
from backend.api.routers.graphs import router as graphs_router
from backend.api.routers.nodes import router as nodes_router
from backend.api.routers.edges import router as edges_router
from backend.api.routers.simulation import router as simulation_router
from backend.api.routers.presets import router as presets_router
from backend.api.routers.grafana_json import router as grafana_json_router
from backend.api.routers.runs import router as runs_router

router = APIRouter()

router.include_router(graphs_router)
router.include_router(nodes_router)
router.include_router(edges_router)
router.include_router(simulation_router)
router.include_router(presets_router)
router.include_router(grafana_json_router)
router.include_router(runs_router)
