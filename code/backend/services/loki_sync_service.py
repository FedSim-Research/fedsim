"""Service to sync evaluation points from database to Loki."""

import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests
from sqlalchemy import select

from backend.db.database import SessionLocal
from backend.db.models import EvaluationPoint, SimulationRun
from backend.services.evaluation_point_store import ensure_run_points
import re

logger = logging.getLogger(__name__)

LOKI_PUSH_URL = "http://loki:3100/loki/api/v1/push"
LOKI_QUERY_URL = "http://loki:3100/loki/api/v1/query_range"


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
            logger.warning(
                "sync_run_to_loki_failed: Run not found in database run_id=%s. "
                "The SimulationRun record must be created before syncing.",
                run_id
            )
            return False

        # Fetch evaluation points for this run, ordered by timestamp
        eval_points = session.execute(
            select(EvaluationPoint)
            .where(EvaluationPoint.run_id == run_id)
            .order_by(EvaluationPoint.timestamp_real)
        ).scalars().all()

        if not eval_points:
            logger.info("sync_run_to_loki: No evaluation points to sync for run: %s", run_id)
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
                        "job": "fedsim-evaluation",
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
            "sync_run_to_loki_success: run_id=%s evaluation_points=%d",
            run_id,
            len(eval_points),
        )
        return True

    except requests.RequestException as e:
        error_msg = str(e)
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_details = e.response.text
                logger.error(
                    "sync_run_to_loki_failed: Loki push failed for run %s: HTTP %d - %s",
                    run_id,
                    e.response.status_code,
                    error_details,
                )
            except Exception:
                logger.error("sync_run_to_loki_failed: Loki push failed for run %s: %s", run_id, error_msg)
        else:
            logger.error("sync_run_to_loki_failed: Loki push failed for run %s: %s", run_id, error_msg)
        return False
    except Exception as e:
        logger.exception("sync_run_to_loki_failed: Unexpected error for run %s", run_id)
        return False
    finally:
        session.close()


def _query_loki_with_strategies(run_id: str, start_ns: int, end_ns: int) -> dict | None:
    """
    Try multiple Loki query strategies to find evaluation logs for a run.
    
    Tries queries in order of preference:
    1. Primary: job="fedsim-evaluation" |= "run_id=..."
    2. Fallback 1: job="ray-actors" |= "run_id=..."
    3. Fallback 2: All logs containing run_id (no job filter)
    
    Returns:
        Response data dict if successful, None otherwise
    """
    escaped_run_id = run_id.replace("\\", "\\\\").replace('"', '\\"')
    
    queries_to_try = [
        # Primary query
        f'{{job="fedsim-evaluation"}} |= "run_id={escaped_run_id}"',
        # Fallback: try ray-actors job (if logs went to different job)
        f'{{job="ray-actors"}} |= "run_id={escaped_run_id}" |= "Eval"',
        # Fallback: try without job label (broader search)
        f'|= "run_id={escaped_run_id}" |= "Eval"',
    ]
    
    for attempt, query in enumerate(queries_to_try, 1):
        try:
            logger.debug("Loki query attempt %d/%d: query=%s", attempt, len(queries_to_try), query)
            
            response = requests.get(
                LOKI_QUERY_URL,
                params={
                    "query": query,
                    "start": start_ns,
                    "end": end_ns,
                    "limit": 10000,
                },
                timeout=30,
            )
            
            logger.debug("Loki query attempt %d response status: %d", attempt, response.status_code)
            response.raise_for_status()
            
            data = response.json()
            if data.get("status") == "success":
                result = data.get("data", {}).get("result", [])
                if result:
                    logger.info("Loki query succeeded at attempt %d: query=%s", attempt, query)
                    return data
                else:
                    logger.debug("Loki query attempt %d returned no results", attempt)
            else:
                error_msg = data.get("error", "Unknown error")
                logger.debug("Loki query attempt %d failed: %s", attempt, error_msg)
        
        except requests.RequestException as e:
            logger.debug("Loki query attempt %d raised exception: %s", attempt, str(e))
            continue
        except Exception as e:
            logger.debug("Loki query attempt %d unexpected error: %s", attempt, str(e))
            continue
    
    # All queries failed
    logger.warning(
        "reconstruct_from_loki: All Loki query strategies failed for run %s. "
        "Logs may not exist in Loki or there may be connectivity issues.",
        run_id
    )
    return None


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
        
        logger.debug("reconstruct_from_loki: Attempting to fetch logs for run %s (24h window)", run_id)
        
        # Try multiple query strategies
        data = _query_loki_with_strategies(run_id, start_ns, now_ns)
        
        if data is None:
            logger.warning("reconstruct_from_loki: Could not query Loki for run %s", run_id)
            return 0
        
        streams = data.get("data", {}).get("result", [])
        if not streams:
            logger.info("reconstruct_from_loki: No logs found in Loki for run: %s", run_id)
            return 0
        
        # Parse log lines and extract evaluation data
        session = SessionLocal()
        inserted = 0
        
        try:
            # Regex to extract evaluation metrics from log format:
            # [hierarchical Eval] run_id=... T=X.XsX | Acc: X.XXX | Loss: X.XXXX
            log_pattern = re.compile(
                r'\[(?P<arch>\w+) Eval\].*?T=\s*(?P<time>[\d.]+)s.*?Acc:\s*(?P<acc>[\d.]+).*?Loss:\s*(?P<loss>[\d.]+)'
            )
            
            for stream in streams:
                labels = stream.get("stream", {})
                architecture = _normalize_architecture_label(str(labels.get("architecture", "unknown")))
                
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
                logger.info("reconstruct_from_loki_success: run_id=%s reconstructed=%d", run_id, inserted)
            else:
                logger.info("reconstruct_from_loki: No parseable log entries found for run %s", run_id)
            
            return inserted
        except Exception as e:
            session.rollback()
            logger.error("reconstruct_from_loki_failed: Error processing Loki results for run %s: %s", run_id, str(e))
            return 0
        finally:
            session.close()
    
    except Exception as e:
        logger.exception("reconstruct_from_loki_failed: Unexpected error for run %s", run_id)
        return 0
