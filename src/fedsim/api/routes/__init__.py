from fastapi import APIRouter

from fedsim.api.routes.edges import router as edges_router
from fedsim.api.routes.grafana_json import router as grafana_json_router
from fedsim.api.routes.graphs import router as graphs_router
from fedsim.api.routes.nodes import router as nodes_router
from fedsim.api.routes.presets import router as presets_router
from fedsim.api.routes.runs import router as runs_router
from fedsim.api.routes.simulation import router as simulation_router

router = APIRouter()

router.include_router(graphs_router)
router.include_router(nodes_router)
router.include_router(edges_router)
router.include_router(simulation_router)
router.include_router(presets_router)
router.include_router(grafana_json_router)
router.include_router(runs_router)
