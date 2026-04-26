from __future__ import annotations

from datetime import datetime
import json
from typing import Any

from sqlalchemy import select

from backend.db.database import SessionLocal
from backend.db.models import SimulationRun

TERMINAL_STATUSES = {"completed", "failed"}


def _loads_json(value: str | None) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _dumps_json(value: dict[str, Any] | None) -> str | None:
    if value is None:
        return None
    return json.dumps(value)


def _iso_to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _datetime_to_iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.isoformat()


def _build_run_metadata(job: Any) -> dict[str, Any]:
    return {
        "graph_id": job.graph_id,
        "architecture": job.architecture,
        "training_config": job.training_config,
        "simulation_settings": job.simulation_settings,
        "spyker_config": job.spyker_config,
        "combined_payload": job.combined_payload,
    }


def _build_final_summary(job: Any) -> dict[str, Any] | None:
    if job.status not in {"completed", "failed"}:
        return None
    result = job.result or {}
    return {
        "status": job.status,
        "duration_seconds": job.duration_seconds,
        "error": job.error,
        "output_filename": result.get("output_filename"),
        "accuracy_loss_snapshot_url": result.get("accuracy_loss_snapshot_url"),
        "accuracy_loss_snapshot_urls_by_architecture": result.get("accuracy_loss_snapshot_urls_by_architecture"),
        "evaluation": result.get("evaluation"),
        "evaluation_summary": result.get("evaluation_summary"),
        "seed": result.get("seed"),
        "seed_set": result.get("seed_set"),
        "repetitions": result.get("repetitions"),
        "completed_repetitions": result.get("completed_repetitions"),
        "runs": result.get("runs"),
        "results_by_architecture": result.get("results_by_architecture"),
    }


def persist_final_run(job: Any) -> None:
    if job.status not in TERMINAL_STATUSES:
        return

    session = SessionLocal()
    try:
        record = session.get(SimulationRun, job.run_id)
        if record is None:
            record = SimulationRun(
                run_id=job.run_id,
                graph_id=job.graph_id,
                architecture=job.architecture,
                status=job.status,
                queued_at=_iso_to_datetime(job.queued_at) or datetime.utcnow(),
            )
            session.add(record)

        record.graph_id = job.graph_id
        record.architecture = job.architecture
        record.status = job.status
        record.queued_at = _iso_to_datetime(job.queued_at) or record.queued_at
        record.started_at = _iso_to_datetime(job.started_at)
        record.finished_at = _iso_to_datetime(job.finished_at)
        record.duration_seconds = job.duration_seconds
        record.error = job.error
        record.metadata_json = _dumps_json(_build_run_metadata(job))
        record.result_json = _dumps_json(job.result)
        record.final_summary_json = _dumps_json(_build_final_summary(job))
        session.commit()
    finally:
        session.close()


def _to_api_dict(record: SimulationRun) -> dict[str, Any]:
    result = _loads_json(record.result_json) or {}
    metadata = _loads_json(record.metadata_json) or {}
    final_summary = _loads_json(record.final_summary_json)
    primary_settings = metadata.get("simulation_settings") or {}
    if record.architecture == "both":
        combined_payload = metadata.get("combined_payload") or {}
        primary_settings = (combined_payload.get("hierfl") or {}).get("simulation_settings") or {}

    dataset = primary_settings.get("dataset") if isinstance(primary_settings, dict) else None
    if not isinstance(dataset, str) or not dataset.strip():
        dataset = None

    datasets_by_architecture: dict[str, str | None] | None = None
    if record.architecture == "both":
        combined_payload = metadata.get("combined_payload") or {}
        hierfl_settings = (combined_payload.get("hierfl") or {}).get("simulation_settings") or {}
        spyker_settings = (combined_payload.get("spyker") or {}).get("simulation_settings") or {}

        def _dataset_from(settings: dict[str, Any]) -> str | None:
            value = settings.get("dataset")
            if isinstance(value, str) and value.strip():
                return value
            return None

        datasets_by_architecture = {
            "hierfl": _dataset_from(hierfl_settings),
            "spyker": _dataset_from(spyker_settings),
        }

    return {
        "run_id": record.run_id,
        "status": record.status,
        "graph_id": record.graph_id,
        "architecture": record.architecture,
        "seed": result.get("seed", primary_settings.get("seed")),
        "seed_set": result.get("seed_set", primary_settings.get("seed_set")),
        "repetitions": result.get("repetitions", primary_settings.get("repetitions")),
        "completed_repetitions": result.get("completed_repetitions"),
        "queued_at": _datetime_to_iso(record.queued_at),
        "started_at": _datetime_to_iso(record.started_at),
        "finished_at": _datetime_to_iso(record.finished_at),
        "duration_seconds": record.duration_seconds,
        "output_filename": result.get("output_filename"),
        "dataset": dataset,
        "datasets_by_architecture": datasets_by_architecture,
        "accuracy_loss_snapshot_url": result.get("accuracy_loss_snapshot_url"),
        "accuracy_loss_snapshot_urls_by_architecture": result.get("accuracy_loss_snapshot_urls_by_architecture"),
        "evaluation": result.get("evaluation"),
        "evaluation_summary": result.get("evaluation_summary"),
        "runs": result.get("runs"),
        "results_by_architecture": result.get("results_by_architecture"),
        "error": record.error,
        "run_metadata": metadata,
        "final_run_summary": final_summary,
    }


def get_run_api(run_id: str) -> dict[str, Any] | None:
    session = SessionLocal()
    try:
        record = session.get(SimulationRun, run_id)
        if record is None:
            return None
        if record.status not in TERMINAL_STATUSES:
            return None
        return _to_api_dict(record)
    finally:
        session.close()


def list_runs_api() -> list[dict[str, Any]]:
    session = SessionLocal()
    try:
        stmt = (
            select(SimulationRun)
            .where(SimulationRun.status.in_(TERMINAL_STATUSES))
            .order_by(SimulationRun.queued_at.desc())
        )
        records = list(session.execute(stmt).scalars().all())
        return [_to_api_dict(record) for record in records]
    finally:
        session.close()
