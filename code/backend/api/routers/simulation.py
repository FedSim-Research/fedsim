from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel
from backend.simulation_controller import SimulationController
from backend.services import graph_service
from backend.services.hierfl_simulation_builder import validate_hierfl_graph

router = APIRouter(tags=["simulation"])

class SimulationTrainingConfig(BaseModel):
    epochs: int
    lr: float


class SimulationSettings(BaseModel):
    run_time_limit: float | None = None
    output_filename: str | None = None
    evaluate_model: bool = False


class SimulationStartRequest(BaseModel):
    graph_id: int
    training_config: SimulationTrainingConfig | None = None
    simulation_settings: SimulationSettings | None = None

class SimulationStartResponse(BaseModel):
    status: str
    graph_id: int
    architecture: str

@router.post("/start_simulation", response_model=SimulationStartResponse, status_code=202)
def start_simulation(
    payload: SimulationStartRequest,
    background_tasks: BackgroundTasks,
):
    graph = graph_service.get_graph(payload.graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    if graph.architecture == "hierfl":
        if payload.training_config is None:
            raise HTTPException(status_code=400, detail="hierfl_missing_training_config")
        if payload.simulation_settings:
            if payload.simulation_settings.evaluate_model and not payload.simulation_settings.output_filename:
                raise HTTPException(status_code=400, detail="hierfl_missing_output_filename")
            if payload.simulation_settings.run_time_limit is not None and payload.simulation_settings.run_time_limit <= 0:
                raise HTTPException(status_code=400, detail="hierfl_invalid_run_time_limit")
        try:
            validate_hierfl_graph(graph)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    controller = SimulationController(
        graph.architecture,
        graph=graph,
        training_config=payload.training_config.model_dump() if payload.training_config else None,
        simulation_settings=payload.simulation_settings.model_dump() if payload.simulation_settings else None,
    )
    background_tasks.add_task(controller.start)

    return {
        "status": "started",
        "graph_id": graph.id,
        "architecture": graph.architecture,
    }