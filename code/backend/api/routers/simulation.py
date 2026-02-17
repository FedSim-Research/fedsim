from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.simulation_controller import SimulationController
from backend.services import graph_service
from backend.services.hierfl_simulation_builder import validate_hierfl_graph
from backend.services.spyker_simulation_builder import validate_spyker_graph

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

    if graph.architecture == "hierfl":
        if payload.training_config is None:
            raise HTTPException(status_code=400, detail="hierfl_missing_training_config")
        if payload.training_config.model_complexity is not None and payload.training_config.model_complexity <= 0:
            raise HTTPException(status_code=400, detail="hierfl_invalid_model_complexity")
        if payload.simulation_settings:
            if payload.simulation_settings.evaluate_model and not payload.simulation_settings.output_filename:
                raise HTTPException(status_code=400, detail="hierfl_missing_output_filename")
            if payload.simulation_settings.run_time_limit is not None and payload.simulation_settings.run_time_limit <= 0:
                raise HTTPException(status_code=400, detail="hierfl_invalid_run_time_limit")
        try:
            validate_hierfl_graph(graph)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if graph.architecture == "spyker":
        if payload.training_config is None:
            raise HTTPException(status_code=400, detail="spyker_missing_training_config")
        if payload.training_config.model_complexity is not None and payload.training_config.model_complexity <= 0:
            raise HTTPException(status_code=400, detail="spyker_invalid_model_complexity")
        if payload.simulation_settings:
            if payload.simulation_settings.evaluate_model and not payload.simulation_settings.output_filename:
                raise HTTPException(status_code=400, detail="spyker_missing_output_filename")
            if payload.simulation_settings.run_time_limit is not None and payload.simulation_settings.run_time_limit <= 0:
                raise HTTPException(status_code=400, detail="spyker_invalid_run_time_limit")
            if payload.simulation_settings.idle_token_delay is not None and payload.simulation_settings.idle_token_delay < 0:
                raise HTTPException(status_code=400, detail="spyker_invalid_idle_token_delay")
        if payload.spyker_config:
            if payload.spyker_config.decay_beta is not None and payload.spyker_config.decay_beta < 0:
                raise HTTPException(status_code=400, detail="spyker_invalid_decay_beta")
            if payload.spyker_config.min_learning_rate is not None and payload.spyker_config.min_learning_rate <= 0:
                raise HTTPException(status_code=400, detail="spyker_invalid_min_learning_rate")
            if payload.spyker_config.h_inter is not None and payload.spyker_config.h_inter < 1:
                raise HTTPException(status_code=400, detail="spyker_invalid_h_inter")
            if payload.spyker_config.h_intra is not None and payload.spyker_config.h_intra < 1:
                raise HTTPException(status_code=400, detail="spyker_invalid_h_intra")
            if payload.spyker_config.sigmoid_phi is not None and payload.spyker_config.sigmoid_phi <= 0:
                raise HTTPException(status_code=400, detail="spyker_invalid_sigmoid_phi")
            if payload.spyker_config.server_learning_rate is not None and payload.spyker_config.server_learning_rate <= 0:
                raise HTTPException(status_code=400, detail="spyker_invalid_server_learning_rate")
            if payload.spyker_config.tcp_rto_delay is not None and payload.spyker_config.tcp_rto_delay < 0:
                raise HTTPException(status_code=400, detail="spyker_invalid_tcp_rto_delay")
        try:
            validate_spyker_graph(graph)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    controller = SimulationController(
        graph.architecture,
        graph=graph,
        training_config=payload.training_config.model_dump() if payload.training_config else None,
        simulation_settings=payload.simulation_settings.model_dump() if payload.simulation_settings else None,
        spyker_config=payload.spyker_config.model_dump() if payload.spyker_config else None,
    )
    result = controller.start()

    return {
        "status": "completed",
        "graph_id": graph.id,
        "architecture": graph.architecture,
        **(result or {}),
    }