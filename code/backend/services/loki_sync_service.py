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
            logger.warning("Run not found: %s", run_id)
            return False

        # Fetch evaluation points for this run, ordered by timestamp
        eval_points = session.execute(
            select(EvaluationPoint)
            .where(EvaluationPoint.run_id == run_id)
            .order_by(EvaluationPoint.timestamp_real)
        ).scalars().all()

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
            "sync_run_to_loki success: run_id=%s points=%d",
            run_id,
            len(eval_points),
        )
        return True

    except requests.RequestException as e:
        logger.error("Loki push failed for run %s: %s", run_id, e)
        return False
    except Exception as e:
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
        query = f'{{job="fedsim-evaluation"}} |= "run_id={run_id}"'
        
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
                logger.info("reconstruct_from_loki success: run_id=%s reconstructed=%d", run_id, inserted)
            
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
    except Exception as e:
        logger.exception("reconstruct_from_loki failed for run %s", run_id)
        return 0
