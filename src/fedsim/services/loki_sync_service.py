"""Service to sync evaluation points from database to Loki."""

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from sqlalchemy import select

from fedsim.persistence.database import SessionLocal
from fedsim.persistence.models import EvaluationPoint, SimulationRun
from fedsim.services.evaluation_point_store import ensure_run_points

logger = logging.getLogger(__name__)

LOKI_PUSH_URL = "http://loki:3100/loki/api/v1/push"
LOKI_QUERY_URL = "http://loki:3100/loki/api/v1/query_range"
LOKI_EVALUATION_JOB_LABEL = "fedsim-evaluation"
_SUPPORTED_EVALUATOR_ARCHITECTURES = {"hierarchical", "spyker"}


def _candidate_ray_log_dirs() -> list[Path]:
    root = Path("/tmp/ray")
    if not root.exists():
        return []

    candidates = [root / "session_latest" / "logs"]
    candidates.extend(sorted(root.glob("session_*/logs"), reverse=True))
    return [path for path in candidates if path.exists()]


def _read_run_logs_from_ray_files(run_id: str) -> str | None:
    for log_dir in _candidate_ray_log_dirs():
        for suffix in ("*.out", "*.log", "*.txt", "*.jsonl"):
            for path in log_dir.rglob(suffix):
                try:
                    content = path.read_text(errors="ignore")
                except Exception:
                    continue
                if run_id not in content:
                    continue
                lines = [line for line in content.splitlines() if run_id in line]
                if lines:
                    return "\n".join(lines)
    return None


def _normalize_architecture_label(value: str) -> str:
    if value == "hierfl":
        return "hierarchical"
    return value


def _format_evaluation_log_line(row: EvaluationPoint) -> str:
    """Format evaluation point as a human-readable log line."""
    architecture = _normalize_architecture_label(row.architecture)
    return (
        f"[{architecture} Eval] run_id={row.run_id} "
        f"T={row.virtual_time:>6.1f}s | Acc: {row.accuracy * 100:>5.2f}% | Loss: {row.loss:.4f}"
    )


def _evaluation_points_for_run(session, run_id: str) -> list[EvaluationPoint]:
    return list(
        session.execute(
            select(EvaluationPoint)
            .where(EvaluationPoint.run_id == run_id)
            .order_by(EvaluationPoint.timestamp_real)
        )
        .scalars()
        .all()
    )


def sync_run_to_loki(run_id: str) -> bool:
    """
    Query evaluation points from DB for a completed run and push to Loki.

    Args:
        run_id: The simulation run ID

    Returns:
        True if sync succeeded, False otherwise
    """
    ensure_run_points(run_id)
    session = SessionLocal()
    try:
        # Fetch run metadata
        run = session.execute(
            select(SimulationRun).where(SimulationRun.run_id == run_id)
        ).scalar_one_or_none()

        if not run:
            logger.warning("Run not found: %s", run_id)
            return False

        # Fetch evaluation points for this run, ordered by timestamp
        eval_points = _evaluation_points_for_run(session, run_id)

        if not eval_points:
            logger.info("No evaluation points to sync for run: %s", run_id)
            return True

        # Build Loki push payload
        # Group entries by (run_id, architecture) to reuse streams efficiently
        streams_dict: dict[tuple[str, str], list[tuple[str, str]]] = {}

        for ep in eval_points:
            timestamp_ns = int(ep.timestamp_real.timestamp() * 1_000_000_000)
            log_line = _format_evaluation_log_line(ep)
            architecture = _normalize_architecture_label(ep.architecture)

            key = (run_id, architecture)
            if key not in streams_dict:
                streams_dict[key] = []

            streams_dict[key].append((str(timestamp_ns), log_line))

        # Convert to Loki stream format
        streams = []
        for (run_id_key, architecture), values in streams_dict.items():
            streams.append(
                {
                    "stream": {
                        "run_id": run_id_key,
                        "architecture": architecture,
                        "job": LOKI_EVALUATION_JOB_LABEL,
                    },
                    "values": values,
                }
            )

        payload = {"streams": streams}

        # Push to Loki
        response = requests.post(
            LOKI_PUSH_URL,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()

        logger.info(
            "sync_run_to_loki success: run_id=%s points=%d",
            run_id,
            len(eval_points),
        )
        return True

    except requests.RequestException as e:
        logger.error("Loki push failed for run %s: %s", run_id, e)
        return False
    except Exception:
        logger.exception("sync_run_to_loki failed for run %s", run_id)
        return False
    finally:
        session.close()


def reconstruct_from_loki(run_id: str) -> int:
    """
    Query evaluation logs from Loki and backfill them into the database.
    Useful for reconstructing data after container restart when DB is empty.

    Args:
        run_id: The simulation run ID

    Returns:
        Number of evaluation points reconstructed from Loki
    """
    try:
        # Query Loki for evaluation logs from this run
        # Use a 24-hour window to catch all evaluations
        now_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        start_ns = now_ns - (86400 * 1_000_000_000)  # 24 hours ago

        # Use line filter for run_id to avoid label cardinality issues
        query = f'{{job="{LOKI_EVALUATION_JOB_LABEL}"}} |= "run_id={run_id}"'

        response = requests.get(
            LOKI_QUERY_URL,
            params={
                "query": query,
                "start": start_ns,
                "end": now_ns,
                "limit": 10000,
            },
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "success":
            logger.warning("Loki query failed for run %s: %s", run_id, data.get("error"))
            return 0

        streams = data.get("data", {}).get("result", [])
        if not streams:
            logger.info("No logs found in Loki for run: %s", run_id)
            return 0

        # Parse log lines and extract evaluation data
        session = SessionLocal()
        inserted = 0

        try:
            # Regex to extract evaluation metrics from log format:
            # [hierarchical Eval] run_id=... T=X.XsX | Acc: X.XXX | Loss: X.XXXX
            log_pattern = re.compile(
                r"\[(?P<arch>\w+) Eval\].*?T=\s*(?P<time>[\d.]+)s.*?Acc:\s*(?P<acc>[\d.]+).*?Loss:\s*(?P<loss>[\d.]+)"
            )

            for stream in streams:
                labels = stream.get("stream", {})
                architecture = _normalize_architecture_label(
                    str(labels.get("architecture", "unknown"))
                )

                values = stream.get("values", [])
                for timestamp_ns_str, log_line in values:
                    match = log_pattern.search(log_line)
                    if not match:
                        continue

                    try:
                        timestamp_ns = int(timestamp_ns_str)
                        virtual_time = float(match.group("time"))
                        accuracy = float(match.group("acc")) / 100.0  # Convert from percentage
                        loss = float(match.group("loss"))

                        timestamp_real = datetime.fromtimestamp(
                            timestamp_ns / 1_000_000_000, tz=timezone.utc
                        )

                        # Check if already exists
                        exists = session.execute(
                            select(EvaluationPoint.id).where(
                                EvaluationPoint.run_id == run_id,
                                EvaluationPoint.architecture == architecture,
                                EvaluationPoint.virtual_time == virtual_time,
                            )
                        ).first()

                        if exists:
                            continue

                        record = EvaluationPoint(
                            run_id=run_id,
                            architecture=architecture,
                            timestamp_real=timestamp_real,
                            virtual_time=virtual_time,
                            round=0,  # Unknown round from log format
                            accuracy=accuracy,
                            loss=loss,
                        )
                        session.add(record)
                        inserted += 1
                    except (ValueError, AttributeError) as e:
                        logger.debug("Failed to parse log line for run %s: %s", run_id, str(e))
                        continue

            if inserted > 0:
                session.commit()
                logger.info(
                    "reconstruct_from_loki success: run_id=%s reconstructed=%d", run_id, inserted
                )

            return inserted
        except Exception as e:
            session.rollback()
            logger.error("reconstruct_from_loki failed for run %s: %s", run_id, str(e))
            return 0
        finally:
            session.close()

    except requests.RequestException as e:
        logger.error("Loki query failed for run %s: %s", run_id, str(e))
        return 0
    except Exception:
        logger.exception("reconstruct_from_loki failed for run %s", run_id)
        return 0


def fetch_run_logs(run_id: str) -> str | None:
    """
    Return the persisted raw evaluator logs for a run.

    Prefers the raw_logs column if it has been populated. Otherwise,
    queries Loki for the exact log lines emitted by the periodic evaluator.
    """
    session = SessionLocal()
    try:
        run = session.execute(
            select(SimulationRun).where(SimulationRun.run_id == run_id)
        ).scalar_one_or_none()
        if run is not None and isinstance(run.raw_logs, str) and run.raw_logs.strip():
            return run.raw_logs
    finally:
        session.close()

    ray_logs = _read_run_logs_from_ray_files(run_id)
    if ray_logs:
        return ray_logs

    try:
        now_ns = int(datetime.now(timezone.utc).timestamp() * 1_000_000_000)
        start_ns = now_ns - (86400 * 1_000_000_000)
        query = f'{{job="{LOKI_EVALUATION_JOB_LABEL}"}} |= "run_id={run_id}"'

        response = requests.get(
            LOKI_QUERY_URL,
            params={
                "query": query,
                "start": start_ns,
                "end": now_ns,
                "limit": 10000,
            },
            timeout=30,
        )
        response.raise_for_status()

        data = response.json()
        if data.get("status") != "success":
            logger.warning("Loki log fetch failed for run %s: %s", run_id, data.get("error"))
            return None

        streams = data.get("data", {}).get("result", [])
        if not streams:
            return None

        entries: list[tuple[int, str]] = []
        for stream in streams:
            values = stream.get("values", [])
            for value_pair in values:
                if not isinstance(value_pair, list) or len(value_pair) < 2:
                    continue
                try:
                    timestamp_ns = int(value_pair[0])
                except (TypeError, ValueError):
                    continue
                line = value_pair[1]
                if not isinstance(line, str):
                    continue
                entries.append((timestamp_ns, line))

        if not entries:
            return None

        entries.sort(key=lambda item: item[0])
        return "\n".join(line for _, line in entries)
    except requests.RequestException as e:
        logger.error("Loki log fetch failed for run %s: %s", run_id, e)
        return None
    except Exception:
        logger.exception("fetch_run_logs failed for run %s", run_id)
        return None
