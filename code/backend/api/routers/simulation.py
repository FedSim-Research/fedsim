from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.simulation_controller import SimulationController
from backend.services import graph_service
from backend.services.simulation_validation import validate_start_payload

router = APIRouter(tags=["simulation"])

class SimulationTrainingConfig(BaseModel):
    epochs: int
    lr: float
    model_complexity: float | None = None


class SimulationSettings(BaseModel):
    run_time_limit: float | None = None
    idle_token_delay: float | None = None
    output_filename: str | None = None
    evaluate_model: bool = False

class SpykerAlgorithmConfig(BaseModel):
    decay_beta: float | None = None
    min_learning_rate: float | None = None
    h_inter: int | None = None
    h_intra: int | None = None
    sigmoid_phi: float | None = None
    server_learning_rate: float | None = None
    tcp_rto_delay: float | None = None


class SimulationStartRequest(BaseModel):
    graph_id: int
    training_config: SimulationTrainingConfig | None = None
    simulation_settings: SimulationSettings | None = None
    spyker_config: SpykerAlgorithmConfig | None = None

class SimulationEvaluationResult(BaseModel):
    accuracy: float
    avg_loss: float

class SimulationStartResponse(BaseModel):
    status: str
    graph_id: int
    architecture: str
    output_filename: str | None = None
    evaluation: SimulationEvaluationResult | None = None

@router.post("/start_simulation", response_model=SimulationStartResponse)
def start_simulation(
    payload: SimulationStartRequest,
):
    graph = graph_service.get_graph(payload.graph_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Graph not found")

    training_config = payload.training_config.model_dump() if payload.training_config else None
    simulation_settings = payload.simulation_settings.model_dump() if payload.simulation_settings else None
    spyker_config = payload.spyker_config.model_dump() if payload.spyker_config else None
    try:
        validate_start_payload(
            architecture=graph.architecture,
            graph=graph,
            training_config=training_config,
            simulation_settings=simulation_settings,
            spyker_config=spyker_config,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    controller = SimulationController(
        graph.architecture,
        graph=graph,
        training_config=training_config,
        simulation_settings=simulation_settings,
        spyker_config=spyker_config,
    )
    result = controller.start()

    return {
        "status": "completed",
        "graph_id": graph.id,
        "architecture": graph.architecture,
        **(result or {}),
    }
