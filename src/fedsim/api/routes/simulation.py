import logging

from fastapi import APIRouter, HTTPException, Response, status
from pydantic import BaseModel, Field

from fedsim.services import graph_service, simulation_run_store
from fedsim.services.evaluation_point_store import evaluation_run_ids, export_evaluation_points
from fedsim.services.run_definition import RunDefinition, read_archived_definition
from fedsim.services.simulation_run_queue import run_queue
from fedsim.services.simulation_seed_sets import (
    normalize_simulation_settings,
    shared_seed_set_or_raise,
)
from fedsim.services.simulation_validation import validate_start_payload

router = APIRouter(tags=["simulation"])
logger = logging.getLogger(__name__)


class SimulationTrainingConfig(BaseModel):
    epochs: int
    lr: float
    model_complexity: float | None = None
    batch_size: int | None = None


class SimulationSettings(BaseModel):
    run_time_limit: float | None = None
    eval_interval: float | None = None
    idle_token_delay: float | None = None
    gpu_budget: float | None = None
    dataset: str | None = None
    seed: int | None = None
    seed_set: list[int] | None = None
    repetitions: int | None = None
    output_filename: str | None = None
    evaluate_model: bool = False


class SpykerAlgorithmConfig(BaseModel):
    decay_beta: float | None = None
    min_learning_rate: float | None = None
    h_inter: int | None = None
    h_intra: int | None = None
    sigmoid_phi: float | None = None
    server_learning_rate: float | None = None
    tcp_rto_delay: float | None = Field(
        default=None,
        description="Reserved compatibility field; not applied by either simulation engine.",
    )


class SimulationStartRequest(BaseModel):
    graph_id: int
    training_config: SimulationTrainingConfig | None = None
    simulation_settings: SimulationSettings | None = None
    spyker_config: SpykerAlgorithmConfig | None = None


class ServerEvaluationResult(BaseModel):
    accuracy: float
    avg_loss: float


class SimulationEvaluationResult(ServerEvaluationResult):
    aggregation: str | None = None
    server_count: int | None = None
    per_server: dict[str, ServerEvaluationResult] | None = None


class SimulationRunResponse(BaseModel):
    run_id: str
    status: str
    graph_id: int | None = None
    architecture: str
    seed: int | None = None
    seed_set: list[int] | None = None
    repetitions: int | None = None
    completed_repetitions: int | None = None
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    current_sim_time: float | None = None
    run_time_limit: float | None = None
    output_filename: str | None = None
    server_checkpoints: dict[str, str] | None = None
    primary_server_id: str | None = None
    dataset: str | None = None
    datasets_by_architecture: dict[str, str | None] | None = None
    accuracy_loss_snapshot_url: str | None = None
    accuracy_loss_snapshot_urls_by_architecture: dict[str, str | None] | None = None
    evaluation: SimulationEvaluationResult | None = None
    evaluation_summary: dict[str, float | int] | None = None
    runs: list[dict] | None = None
    results_by_architecture: dict[str, dict] | None = None
    error: str | None = None
    run_metadata: dict | None = None
    final_run_summary: dict | None = None


class SimulationSingleConfig(BaseModel):
    graph_id: int
    training_config: SimulationTrainingConfig | None = None
    simulation_settings: SimulationSettings | None = None
    spyker_config: SpykerAlgorithmConfig | None = None


class SimulationStartBothRequest(BaseModel):
    hierfl: SimulationSingleConfig
    spyker: SimulationSingleConfig


@router.post("/start_simulation", response_model=SimulationRunResponse)
def start_simulation(payload: SimulationStartRequest):
    logger.info("start_simulation_requested graph_id=%s", payload.graph_id)
    graph = graph_service.get_graph(payload.graph_id)
    if graph is None:
        logger.warning("start_simulation_graph_not_found graph_id=%s", payload.graph_id)
        raise HTTPException(status_code=404, detail="Graph not found")

    try:
        training_config = payload.training_config.model_dump() if payload.training_config else None
        simulation_settings = normalize_simulation_settings(
            payload.simulation_settings.model_dump() if payload.simulation_settings else None,
            error_prefix=graph.architecture,
        )
        spyker_config = payload.spyker_config.model_dump() if payload.spyker_config else None
        validate_start_payload(
            architecture=graph.architecture,
            graph=graph,
            training_config=training_config,
            simulation_settings=simulation_settings,
            spyker_config=spyker_config,
        )
        definition = RunDefinition.capture(
            {
                graph.architecture: {
                    "graph": graph,
                    "training_config": training_config,
                    "simulation_settings": simulation_settings,
                    "spyker_config": spyker_config,
                }
            }
        )
    except ValueError as exc:
        logger.warning(
            "start_simulation_validation_failed graph_id=%s architecture=%s error=%s",
            graph.id,
            graph.architecture,
            str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run = run_queue.enqueue(definition)
    logger.info(
        "start_simulation_queued run_id=%s graph_id=%s architecture=%s",
        run.run_id,
        graph.id,
        graph.architecture,
    )
    return run.to_api_dict()


@router.post("/start_simulation_both", response_model=SimulationRunResponse)
def start_simulation_both(payload: SimulationStartBothRequest):
    hierfl_graph = graph_service.get_graph(payload.hierfl.graph_id)
    if hierfl_graph is None or hierfl_graph.architecture != "hierfl":
        raise HTTPException(status_code=404, detail="HierFL graph not found")

    spyker_graph = graph_service.get_graph(payload.spyker.graph_id)
    if spyker_graph is None or spyker_graph.architecture != "spyker":
        raise HTTPException(status_code=404, detail="Spyker graph not found")

    try:
        hierfl_training = (
            payload.hierfl.training_config.model_dump() if payload.hierfl.training_config else None
        )
        hierfl_settings = normalize_simulation_settings(
            payload.hierfl.simulation_settings.model_dump()
            if payload.hierfl.simulation_settings
            else None,
            error_prefix="hierfl",
        )
        spyker_training = (
            payload.spyker.training_config.model_dump() if payload.spyker.training_config else None
        )
        spyker_settings = normalize_simulation_settings(
            payload.spyker.simulation_settings.model_dump()
            if payload.spyker.simulation_settings
            else None,
            error_prefix="spyker",
        )
        spyker_algo = (
            payload.spyker.spyker_config.model_dump() if payload.spyker.spyker_config else None
        )
        shared_seed_set_or_raise(hierfl_settings, spyker_settings)
        validate_start_payload(
            architecture="hierfl",
            graph=hierfl_graph,
            training_config=hierfl_training,
            simulation_settings=hierfl_settings,
            spyker_config=None,
        )
        validate_start_payload(
            architecture="spyker",
            graph=spyker_graph,
            training_config=spyker_training,
            simulation_settings=spyker_settings,
            spyker_config=spyker_algo,
        )
        definition = RunDefinition.capture(
            {
                "hierfl": {
                    "graph": hierfl_graph,
                    "training_config": hierfl_training,
                    "simulation_settings": hierfl_settings,
                },
                "spyker": {
                    "graph": spyker_graph,
                    "training_config": spyker_training,
                    "simulation_settings": spyker_settings,
                    "spyker_config": spyker_algo,
                },
            }
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    run = run_queue.enqueue(definition)
    return run.to_api_dict()


@router.get("/runs/{run_id}", response_model=SimulationRunResponse)
def get_run_status(run_id: str):
    run = run_queue.get_run_api(run_id)
    if run is None:
        logger.warning("get_run_status_not_found run_id=%s", run_id)
        raise HTTPException(status_code=404, detail="Run not found")

    logger.debug("get_run_status run_id=%s status=%s", run_id, run.get("status"))
    return run


@router.get("/runs", response_model=list[SimulationRunResponse])
def list_runs():
    return run_queue.list_runs_api()


@router.delete("/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_run(run_id: str):
    try:
        deleted = run_queue.delete_run_api(run_id)
    except ValueError as exc:
        if str(exc) == "run_not_deletable":
            raise HTTPException(
                status_code=409, detail="Only completed or failed runs can be deleted"
            ) from exc
        raise

    if not deleted:
        raise HTTPException(status_code=404, detail="Run not found")


@router.get("/runs/{run_id}/export/csv")
def export_run_to_csv(run_id: str):
    csv_content = simulation_run_store.export_run_to_csv(run_id)
    if csv_content is None:
        raise HTTPException(status_code=404, detail="Run not found")

    return Response(
        content=csv_content,
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename=run_{run_id}.csv"},
    )


@router.get("/runs/{run_id}/export/definition")
def export_run_definition(run_id: str):
    definition = read_archived_definition(run_id)
    if definition is None:
        raise HTTPException(status_code=404, detail="Run definition not available")
    return definition


@router.get("/runs/{run_id}/export/evaluations")
def export_run_evaluations(run_id: str) -> list[dict]:
    run = run_queue.get_run_api(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return export_evaluation_points(evaluation_run_ids(run_id, run))
