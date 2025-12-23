from fastapi import APIRouter
from backend.config.config_loader import load_config, SimulationConfig
from backend.simulation_controller import SimulationController

router = APIRouter(tags=["simulation"])

@router.post("/start_simulation")
def start_simulation(config: SimulationConfig | None = None):
    if config is None:
        config = load_config()

    controller = SimulationController(config)
    controller.start()

    return {"status": "started"}