from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import select

from fedsim.persistence.database import SessionLocal
from fedsim.persistence.models import EvaluationPoint, SimulationRun
from fedsim.settings import telemetry_log_path

logger = logging.getLogger(__name__)

_PERIODIC_EVALUATION_LOG_TYPE = "periodic_evaluation"


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _json_dumps(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, default=str)


def _json_loads(value: str | None) -> dict[str, Any]:
    if not value:
        return {}
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _candidate_log_paths(run_id: str, log_dir: str | Path | None = None) -> list[Path]:
    path = telemetry_log_path(run_id)
    if log_dir is not None:
        return [Path(log_dir) / path.name, path]
    return [path]


def _build_log_line(extra_data: dict[str, Any]) -> str:
    architecture = str(extra_data.get("architecture", "unknown"))
    run_id = str(extra_data.get("run_id", "unknown"))
    virtual_time = float(extra_data.get("virtual_time", 0.0))
    accuracy = float(extra_data.get("accuracy", 0.0))
    loss = float(extra_data.get("loss", 0.0))
    return (
        f"[{architecture} Eval] run_id={run_id} "
        f"T={virtual_time:>6.1f}s | Acc: {accuracy * 100:>5.2f} | Loss: {loss:.4f}"
    )


def _row_to_point(row: EvaluationPoint) -> dict[str, Any]:
    return {
        "run_id": row.run_id,
        "graph_id": row.graph_id,
        "architecture": row.architecture,
        "timestamp_real": row.timestamp_real,
        "virtual_time": row.virtual_time,
        "round": row.round,
        "accuracy": row.accuracy,
        "loss": row.loss,
        "server_stats": _json_loads(row.server_stats_json),
        "line": _build_log_line(
            {
                "run_id": row.run_id,
                "architecture": row.architecture,
                "virtual_time": row.virtual_time,
                "accuracy": row.accuracy,
                "loss": row.loss,
            }
        ),
    }


def persist_periodic_evaluation(
    extra_data: dict[str, Any], timestamp_real: str | None = None
) -> bool:
    if extra_data.get("log_type") != _PERIODIC_EVALUATION_LOG_TYPE:
        return False

    run_id = extra_data.get("run_id")
    architecture = extra_data.get("architecture")
    if not isinstance(run_id, str) or not run_id.strip():
        return False
    if not isinstance(architecture, str) or not architecture.strip():
        return False

    try:
        virtual_time = float(extra_data.get("virtual_time", 0.0))
        round_value = int(extra_data.get("round", 0))
        accuracy = float(extra_data.get("accuracy", 0.0))
        loss = float(extra_data.get("loss", 0.0))
    except (TypeError, ValueError):
        return False

    server_stats = extra_data.get("server_stats")
    if timestamp_real is None:
        timestamp_real = datetime.now(timezone.utc).isoformat()

    session = SessionLocal()
    try:
        record = EvaluationPoint(
            run_id=run_id,
            graph_id=extra_data.get("graph_id"),
            architecture=architecture,
            timestamp_real=_parse_datetime(timestamp_real) or datetime.now(timezone.utc),
            virtual_time=virtual_time,
            round=round_value,
            accuracy=accuracy,
            loss=loss,
            server_stats_json=_json_dumps(server_stats),
        )
        session.add(record)
        session.commit()
        return True
    except Exception:
        session.rollback()
        logger.exception(
            "evaluation_point_persist_failed run_id=%s architecture=%s", run_id, architecture
        )
        return False
    finally:
        session.close()


def backfill_periodic_evaluations_from_log_file(
    run_id: str, log_dir: str | Path | None = None
) -> int:
    for candidate in _candidate_log_paths(run_id, log_dir):
        if not candidate.exists():
            continue

        inserted = 0
        session = SessionLocal()
        try:
            with candidate.open("r", encoding="utf-8") as handle:
                for line_number, raw_line in enumerate(handle, 1):
                    raw_line = raw_line.strip()
                    if not raw_line:
                        continue
                    try:
                        payload = json.loads(raw_line)
                    except json.JSONDecodeError:
                        continue

                    extra_data = payload.get("extra_data", payload)
                    if (
                        not isinstance(extra_data, dict)
                        or extra_data.get("log_type") != _PERIODIC_EVALUATION_LOG_TYPE
                    ):
                        continue

                    record = EvaluationPoint(
                        run_id=str(extra_data.get("run_id", run_id)),
                        graph_id=extra_data.get("graph_id"),
                        architecture=str(extra_data.get("architecture", "unknown")),
                        timestamp_real=_parse_datetime(payload.get("timestamp_real"))
                        or datetime.now(timezone.utc),
                        virtual_time=float(extra_data.get("virtual_time", 0.0)),
                        round=int(extra_data.get("round", 0)),
                        accuracy=float(extra_data.get("accuracy", 0.0)),
                        loss=float(extra_data.get("loss", 0.0)),
                        server_stats_json=_json_dumps(extra_data.get("server_stats")),
                    )
                    exists = session.execute(
                        select(EvaluationPoint.id).where(
                            EvaluationPoint.run_id == record.run_id,
                            EvaluationPoint.architecture == record.architecture,
                            EvaluationPoint.virtual_time == record.virtual_time,
                            EvaluationPoint.round == record.round,
                        )
                    ).first()
                    if exists is not None:
                        continue
                    session.add(record)
                    inserted += 1
            session.commit()
            if inserted:
                logger.info(
                    "evaluation_point_backfill_complete run_id=%s inserted=%s source=%s",
                    run_id,
                    inserted,
                    candidate,
                )
            return inserted
        except Exception:
            session.rollback()
            logger.exception(
                "evaluation_point_backfill_failed run_id=%s source=%s", run_id, candidate
            )
            return 0
        finally:
            session.close()

    return 0


def ensure_run_points(run_id: str) -> None:
    session = SessionLocal()
    try:
        exists = session.execute(
            select(EvaluationPoint.id).where(EvaluationPoint.run_id == run_id).limit(1)
        ).first()
        if exists is not None:
            return
    finally:
        session.close()

    backfill_periodic_evaluations_from_log_file(run_id)


def get_matching_run_ids(run_id_regex: str) -> list[str]:
    pattern = re.compile(run_id_regex)
    session = SessionLocal()
    try:
        rows = session.execute(
            select(SimulationRun.run_id).order_by(SimulationRun.queued_at.desc())
        ).all()
        run_ids = [str(row[0]) for row in rows if pattern.search(str(row[0]))]
        return run_ids
    finally:
        session.close()


def get_evaluation_rows(
    run_id_regex: str = ".*",
    architecture_regex: str = ".*",
    start_ms: int | None = None,
    end_ms: int | None = None,
) -> list[dict[str, Any]]:
    run_pattern = re.compile(run_id_regex)
    architecture_pattern = re.compile(architecture_regex)
    run_ids = get_matching_run_ids(run_id_regex)

    for run_id in run_ids:
        ensure_run_points(run_id)

    # fetch run metadata so we can treat completed runs as "final":
    # for completed runs, only return evaluation points recorded up to finished_at
    session = SessionLocal()
    try:
        runs = session.execute(
            select(SimulationRun.run_id, SimulationRun.finished_at, SimulationRun.status).where(
                SimulationRun.run_id.in_(run_ids)
            )
        ).all()
        run_info: dict[str, dict[str, Any] | None] = {
            str(row[0]): {"finished_at": row[1], "status": row[2]} for row in runs
        }

        stmt = select(EvaluationPoint).where(EvaluationPoint.run_id.in_(run_ids))
        records = list(session.execute(stmt).scalars().all())
    finally:
        session.close()

    output: list[dict[str, Any]] = []
    for record in records:
        if not run_pattern.search(record.run_id):
            continue
        if not architecture_pattern.search(record.architecture):
            continue

        # If the run has a finished_at timestamp, treat points after that as out-of-scope
        info = run_info.get(record.run_id)
        if info is not None:
            finished_at = info.get("finished_at")
            if finished_at is not None and record.timestamp_real > finished_at:
                # Skip points that were recorded after the run finished (defensive)
                continue

        timestamp_ms = int(record.timestamp_real.timestamp() * 1000)
        if start_ms is not None and timestamp_ms < start_ms:
            continue
        if end_ms is not None and timestamp_ms > end_ms:
            continue

        output.append(_row_to_point(record))

    output.sort(key=lambda item: (item["timestamp_real"], item["virtual_time"], item["run_id"]))
    return output
