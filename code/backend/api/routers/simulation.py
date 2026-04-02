from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.simulation_controller import SimulationController
from backend.services import graph_service
from backend.services.simulation_validation import validate_start_payload

router = APIRouter(tags=["simulation"])

_runs_lock = Lock()
_runs_order: list[str] = []
_runs_by_id: dict[str, dict] = {}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _create_run_record(*, graph_id: int, architecture: str, seed: int | None) -> dict:
    run_id = str(uuid4())
    now = _utc_now_iso()
    run = {
        "run_id": run_id,
        "status": "queued",
        "graph_id": graph_id,
        "architecture": architecture,
        "seed": seed,
        "queued_at": now,
        "started_at": None,
        "finished_at": None,
        "duration_seconds": None,
        "output_filename": None,
        "evaluation": None,
        "error": None,
    }
    with _runs_lock:
        _runs_by_id[run_id] = run
        _runs_order.append(run_id)
    return run


def _update_run(run_id: str, **updates) -> dict:
    with _runs_lock:
        current = _runs_by_id.get(run_id)
        if current is None:
            raise KeyError(run_id)
        current.update(updates)
        return dict(current)


def _list_runs_latest_first() -> list[dict]:
    with _runs_lock:
        return [dict(_runs_by_id[run_id]) for run_id in reversed(_runs_order)]


def _get_run(run_id: str) -> dict | None:
    with _runs_lock:
        run = _runs_by_id.get(run_id)
        return dict(run) if run is not None else None

class SimulationTrainingConfig(BaseModel):
    epochs: int
    lr: float
    model_complexity: float | None = None


class SimulationSettings(BaseModel):
    run_time_limit: float | None = None
    idle_token_delay: float | None = None
    seed: int | None = None
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
    run_id: str | None = None
    status: str
    graph_id: int
    architecture: str
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    seed: int | None = None
    output_filename: str | None = None
    evaluation: SimulationEvaluationResult | None = None


class SimulationRunResponse(BaseModel):
    run_id: str
    status: str
    graph_id: int
    architecture: str
    queued_at: str | None = None
    started_at: str | None = None
    finished_at: str | None = None
    duration_seconds: float | None = None
    seed: int | None = None
    output_filename: str | None = None
    evaluation: SimulationEvaluationResult | None = None
    error: str | None = None


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

    run = _create_run_record(
        graph_id=graph.id,
        architecture=graph.architecture,
        seed=simulation_settings.get("seed") if simulation_settings else None,
    )
    started_at = _utc_now_iso()
    _update_run(run["run_id"], status="running", started_at=started_at)

    controller = SimulationController(
        graph.architecture,
        graph=graph,
        training_config=training_config,
        simulation_settings=simulation_settings,
        spyker_config=spyker_config,
    )
    try:
        result = controller.start()
    except Exception as exc:
        finished_at = _utc_now_iso()
        started_dt = datetime.fromisoformat(started_at)
        finished_dt = datetime.fromisoformat(finished_at)
        duration_seconds = (finished_dt - started_dt).total_seconds()
        _update_run(
            run["run_id"],
            status="failed",
            finished_at=finished_at,
            duration_seconds=duration_seconds,
            error=str(exc),
        )
        raise

    finished_at = _utc_now_iso()
    started_dt = datetime.fromisoformat(started_at)
    finished_dt = datetime.fromisoformat(finished_at)
    duration_seconds = (finished_dt - started_dt).total_seconds()
    updated = _update_run(
        run["run_id"],
        status="completed",
        finished_at=finished_at,
        duration_seconds=duration_seconds,
        output_filename=(result or {}).get("output_filename"),
        evaluation=(result or {}).get("evaluation"),
        seed=(result or {}).get("seed"),
    )

    return {
        "run_id": updated["run_id"],
        "status": updated["status"],
        "graph_id": graph.id,
        "architecture": graph.architecture,
        "queued_at": updated["queued_at"],
        "started_at": updated["started_at"],
        "finished_at": updated["finished_at"],
        "duration_seconds": updated["duration_seconds"],
        **(result or {}),
    }


@router.get("/runs", response_model=list[SimulationRunResponse])
def list_runs():
    return _list_runs_latest_first()


@router.get("/runs/{run_id}", response_model=SimulationRunResponse)
def get_run(run_id: str):
    run = _get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return run
