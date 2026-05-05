from __future__ import annotations

from datetime import datetime
import csv
import logging
import json
import os
import re
import time
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import select

from backend.db.database import SessionLocal
from backend.db.models import SimulationRun
from backend.services.evaluation_point_store import ensure_run_points, _candidate_log_paths

TERMINAL_STATUSES = {"completed", "failed"}
DEFAULT_RUNS_CSV_PATH = Path(__file__).resolve().parent.parent / "data" / "simulation_runs.csv"
RUNS_CSV_PATH_ENV_VAR = "FEDSIM_RUNS_CSV_PATH"
logger = logging.getLogger(__name__)

_PERIODIC_EVALUATOR_T_RE = re.compile(r"\bT=\s*(?P<time>[0-9]+(?:\.[0-9]+)?)s\b")


CSV_FIELDNAMES = [
    "run_id",
    "graph_id",
    "architecture",
    "status",
    "queued_at",
    "started_at",
    "finished_at",
    "duration_seconds",
    "error",
    "metadata_json",
    "result_json",
    "final_summary_json",
    "training_config_json",
    "simulation_settings_json",
    "spyker_config_json",
    "combined_payload_json",
    "evaluation_json",
    "evaluation_accuracy",
    "evaluation_avg_loss",
    "evaluation_summary_json",
]


def _run_time_limit_from_settings(
    simulation_settings: dict[str, Any] | None,
    combined_payload: dict[str, Any] | None,
    architecture: str,
) -> float | None:
    if architecture == "both":
        settings = ((combined_payload or {}).get("hierfl") or {}).get("simulation_settings") or {}
    else:
        settings = simulation_settings or {}

    value = settings.get("run_time_limit")
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _loki_base_urls() -> list[str]:
    configured = [
        os.getenv("FEDSIM_LOKI_INTERNAL_BASE_URL", "").strip(),
        os.getenv("FEDSIM_LOKI_BASE_URL", "").strip(),
    ]
    urls = [url.rstrip("/") for url in configured if url]
    if not urls:
        urls.extend(["http://localhost:3100", "http://loki:3100"])
    elif "http://localhost:3100" not in urls:
        urls.append("http://localhost:3100")
    if "http://loki:3100" not in urls:
        urls.append("http://loki:3100")
    return urls


def _current_sim_time_from_loki(run_id: str, architecture: str) -> float | None:
    query = f'{{component="ray", job="ray-actors"}} |= "run_id={run_id}" |= "T="'
    if architecture in {"hierarchical", "spyker"}:
        query += f' |~ "\\[{architecture} Eval\\]"'

    end_ns = int(time.time() * 1_000_000_000)
    start_ns = end_ns - int(24 * 60 * 60 * 1_000_000_000)

    for base_url in _loki_base_urls():
        try:
            response = requests.get(
                f"{base_url}/loki/api/v1/query_range",
                params={
                    "query": query,
                    "start": start_ns,
                    "end": end_ns,
                    "limit": 50,
                    "direction": "backward",
                },
                timeout=8,
            )
        except requests.RequestException:
            continue

        if response.status_code >= 400:
            continue

        payload = response.json()
        results = payload.get("data", {}).get("result", [])
        latest_line: str | None = None
        latest_ts = -1
        for item in results:
            values = item.get("values", [])
            for value_pair in values:
                if not isinstance(value_pair, list) or len(value_pair) < 2:
                    continue
                try:
                    ts = int(value_pair[0])
                except (TypeError, ValueError):
                    continue
                line = value_pair[1]
                if not isinstance(line, str):
                    continue
                if ts >= latest_ts:
                    latest_ts = ts
                    latest_line = line

        if not latest_line:
            continue

        match = _PERIODIC_EVALUATOR_T_RE.search(latest_line)
        if match is None:
            continue

        try:
            return float(match.group("time"))
        except ValueError:
            continue

    return None


def _current_sim_time_from_raw_sources(run_id: str, architecture: str) -> float | None:
    """Fallback: look for T= values in persisted raw_logs or candidate log files on disk."""
    # 1) Check persisted raw_logs in DB
    session = SessionLocal()
    try:
        record = session.get(SimulationRun, run_id)
        if record and isinstance(record.raw_logs, str) and record.raw_logs:
            # Try parsing JSONL lines first (virtual_time field), otherwise fallback to T= regex
            latest: float | None = None
            for raw_line in (record.raw_logs or "").splitlines():
                raw_line = raw_line.strip()
                if not raw_line:
                    continue
                try:
                    payload = json.loads(raw_line)
                    extra = payload.get("extra_data") or payload
                    if isinstance(extra, dict):
                        vt = extra.get("virtual_time")
                        if vt is not None:
                            try:
                                value = float(vt)
                                latest = value if latest is None or value > latest else latest
                                continue
                            except Exception:
                                pass
                except Exception:
                    pass

                m = _PERIODIC_EVALUATOR_T_RE.search(raw_line)
                if m:
                    try:
                        value = float(m.group("time"))
                        latest = value if latest is None or value > latest else latest
                    except Exception:
                        pass

            if latest is not None:
                return latest
    finally:
        session.close()

    # 2) Check candidate log files on disk (JSONL or worker stdout)
    for candidate in _candidate_log_paths(run_id):
        try:
            if not candidate.exists() or not candidate.is_file():
                continue
            text = candidate.read_text(errors="ignore")
        except Exception:
            continue
        # JSONL lines may contain extra_data with virtual_time, or plain stdout with T= marker
        # First try JSON parse per-line
        latest: float | None = None
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            # try JSON payload
            try:
                payload = json.loads(line)
                extra = payload.get("extra_data") or payload
                vt = extra.get("virtual_time") if isinstance(extra, dict) else None
                if vt is not None:
                    try:
                        value = float(vt)
                        latest = value if latest is None or value > latest else latest
                        continue
                    except Exception:
                        pass
            except Exception:
                pass

            # fallback: regex search in the line
            m = _PERIODIC_EVALUATOR_T_RE.search(line)
            if m:
                try:
                    value = float(m.group("time"))
                    latest = value if latest is None or value > latest else latest
                except Exception:
                    continue

        if latest is not None:
            return latest

    return None


def get_run_progress_info(
    run_id: str,
    *,
    architecture: str,
    status: str | None = None,
    simulation_settings: dict[str, Any] | None = None,
    combined_payload: dict[str, Any] | None = None,
) -> dict[str, float | None]:
    current_sim_time = _current_sim_time_from_loki(run_id, architecture)
    # Loki may be unavailable or not indexed; try DB/file fallbacks
    if current_sim_time is None:
        current_sim_time = _current_sim_time_from_raw_sources(run_id, architecture)
    if current_sim_time is None and status in {"queued", "running"}:
        current_sim_time = 0.0

    return {
        "current_sim_time": current_sim_time,
        "run_time_limit": _run_time_limit_from_settings(simulation_settings, combined_payload, architecture),
    }


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
    return json.dumps(value, sort_keys=True, default=str)


def _csv_export_path() -> Path:
    configured = os.getenv(RUNS_CSV_PATH_ENV_VAR, "").strip()
    if configured:
        return Path(configured).expanduser()
    return DEFAULT_RUNS_CSV_PATH


def _csv_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (dict, list)):
        return json.dumps(value, sort_keys=True, default=str)
    return str(value)


def _csv_row_for_run(record: SimulationRun) -> dict[str, str]:
    metadata = _loads_json(record.metadata_json) or {}
    result = _loads_json(record.result_json) or {}
    final_summary = _loads_json(record.final_summary_json) or {}

    evaluation = result.get("evaluation")
    evaluation_summary = result.get("evaluation_summary")
    if evaluation is None and isinstance(final_summary, dict):
        evaluation = final_summary.get("evaluation")
        evaluation_summary = evaluation_summary or final_summary.get("evaluation_summary")

    evaluation_accuracy = ""
    evaluation_avg_loss = ""
    if isinstance(evaluation, dict):
        accuracy = evaluation.get("accuracy")
        avg_loss = evaluation.get("avg_loss")
        evaluation_accuracy = "" if accuracy is None else str(accuracy)
        evaluation_avg_loss = "" if avg_loss is None else str(avg_loss)

    return {
        "run_id": record.run_id,
        "graph_id": _csv_value(record.graph_id),
        "architecture": record.architecture,
        "status": record.status,
        "queued_at": _csv_value(record.queued_at),
        "started_at": _csv_value(record.started_at),
        "finished_at": _csv_value(record.finished_at),
        "duration_seconds": _csv_value(record.duration_seconds),
        "error": _csv_value(record.error),
        "metadata_json": _csv_value(metadata),
        "result_json": _csv_value(result),
        "final_summary_json": _csv_value(final_summary),
        "training_config_json": _csv_value(metadata.get("training_config")),
        "simulation_settings_json": _csv_value(metadata.get("simulation_settings")),
        "spyker_config_json": _csv_value(metadata.get("spyker_config")),
        "combined_payload_json": _csv_value(metadata.get("combined_payload")),
        "evaluation_json": _csv_value(evaluation),
        "evaluation_accuracy": evaluation_accuracy,
        "evaluation_avg_loss": evaluation_avg_loss,
        "evaluation_summary_json": _csv_value(evaluation_summary),
    }


def refresh_runs_csv() -> Path:
    export_path = _csv_export_path()
    export_path.parent.mkdir(parents=True, exist_ok=True)

    session = SessionLocal()
    try:
        stmt = (
            select(SimulationRun)
            .where(SimulationRun.status.in_(TERMINAL_STATUSES))
            .order_by(SimulationRun.queued_at.desc())
        )
        records = list(session.execute(stmt).scalars().all())
    finally:
        session.close()

    temp_path = export_path.parent / f"{export_path.name}.tmp"
    with temp_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        for record in records:
            writer.writerow(_csv_row_for_run(record))

    temp_path.replace(export_path)
    return export_path


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
        # attempt to persist raw JSONL logs (non-blocking)
        try:
            for candidate in _candidate_log_paths(job.run_id):
                if candidate.exists():
                    try:
                        content = candidate.read_text(encoding="utf-8")
                    except Exception:
                        content = None
                    if content:
                        record.raw_logs = (record.raw_logs or "") + "\n" + content
                        break
        except Exception:
            logger.exception("raw_log_persist_failed run_id=%s", job.run_id)
        session.commit()
        try:
            refresh_runs_csv()
        except Exception:
            logger.exception("simulation_run_csv_export_failed run_id=%s", job.run_id)
        # backfill evaluation points from any actor JSONL logs (safe, non-blocking)
        try:
            ensure_run_points(job.run_id)
        except Exception:
            logger.exception("evaluation_point_backfill_failed run_id=%s", job.run_id)
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

    progress_info = get_run_progress_info(
        record.run_id,
        architecture=record.architecture,
        status=record.status,
        simulation_settings=metadata.get("simulation_settings") if isinstance(metadata.get("simulation_settings"), dict) else None,
        combined_payload=metadata.get("combined_payload") if isinstance(metadata.get("combined_payload"), dict) else None,
    )

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
        "current_sim_time": progress_info["current_sim_time"],
        "run_time_limit": progress_info["run_time_limit"],
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


def delete_run_api(run_id: str) -> bool:
    session = SessionLocal()
    try:
        record = session.get(SimulationRun, run_id)
        if record is None:
            return False
        session.delete(record)
        session.commit()
        return True
    finally:
        session.close()


def export_run_to_csv(run_id: str) -> str | None:
    """Export a single run to CSV format string."""
    session = SessionLocal()
    try:
        record = session.get(SimulationRun, run_id)
        if record is None:
            return None
        
        output = []
        import io
        buffer = io.StringIO()
        writer = csv.DictWriter(buffer, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerow(_csv_row_for_run(record))
        output = buffer.getvalue()
        buffer.close()
        return output
    finally:
        session.close()
