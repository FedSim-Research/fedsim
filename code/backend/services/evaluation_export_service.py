"""
Service for parsing JSONL evaluation logs and exporting timeseries data.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from backend.db.database import SessionLocal
from backend.db.models import SimulationRun

logger = logging.getLogger(__name__)


class EvaluationPoint:
    """Single evaluation record from logs."""
    
    def __init__(
        self,
        run_id: str,
        timestamp: str,
        virtual_time: float,
        round_num: int,
        accuracy: float,
        loss: float,
        architecture: str,
        graph_id: int | None = None,
        server_stats: dict[str, Any] | None = None,
    ):
        self.run_id = run_id
        self.timestamp = timestamp
        self.virtual_time = virtual_time
        self.round = round_num
        self.accuracy = accuracy
        self.loss = loss
        self.architecture = architecture
        self.graph_id = graph_id
        self.server_stats = server_stats or {}
    
    def to_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "timestamp": self.timestamp,
            "virtual_time": self.virtual_time,
            "round": self.round,
            "accuracy": self.accuracy,
            "loss": self.loss,
            "architecture": self.architecture,
            "graph_id": self.graph_id,
        }


def parse_evaluation_logs(run_id: str, log_dir: str = "logs") -> list[EvaluationPoint]:
    """
    Parse JSONL evaluation logs for a specific run.
    
    Args:
        run_id: The simulation run ID
        log_dir: Directory containing log files (default: "logs")
    
    Returns:
        List of EvaluationPoint objects sorted by virtual_time
    """
    log_path = Path(log_dir) / f"sim_{run_id}.jsonl"
    
    if not log_path.exists():
        logger.warning(f"Log file not found: {log_path}")
        return []
    
    evaluation_points: list[EvaluationPoint] = []
    
    try:
        with open(log_path, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if not line.strip():
                    continue
                
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to parse JSON at {log_path}:{line_num}: {e}")
                    continue
                
                # Extract evaluation logs (log_type == "periodic_evaluation")
                extra_data = record.get("extra_data", {})
                if extra_data.get("log_type") != "periodic_evaluation":
                    continue
                
                try:
                    point = EvaluationPoint(
                        run_id=extra_data.get("run_id", run_id),
                        timestamp=record.get("timestamp_real", ""),
                        virtual_time=float(extra_data.get("virtual_time", 0)),
                        round_num=int(extra_data.get("round", 0)),
                        accuracy=float(extra_data.get("accuracy", 0)),
                        loss=float(extra_data.get("loss", 0)),
                        architecture=extra_data.get("architecture", "unknown"),
                        graph_id=extra_data.get("graph_id"),
                        server_stats=extra_data.get("server_stats", {}),
                    )
                    evaluation_points.append(point)
                except (ValueError, TypeError) as e:
                    logger.warning(f"Failed to create EvaluationPoint from {log_path}:{line_num}: {e}")
                    continue
    except Exception as e:
        logger.error(f"Error reading log file {log_path}: {e}")
        return []
    
    # Sort by virtual_time
    evaluation_points.sort(key=lambda p: p.virtual_time)
    logger.info(f"Parsed {len(evaluation_points)} evaluation points from {run_id}")
    return evaluation_points


def get_all_run_evaluations(run_ids: list[str] | None = None, log_dir: str = "logs") -> dict[str, list[EvaluationPoint]]:
    """
    Parse evaluation logs for multiple runs.
    
    Args:
        run_ids: Specific run IDs to parse. If None, parses all terminal runs in database.
        log_dir: Directory containing log files
    
    Returns:
        Dict mapping run_id to list of EvaluationPoints
    """
    if run_ids is None:
        # Get terminal runs from database
        session = SessionLocal()
        try:
            from sqlalchemy import select
            stmt = select(SimulationRun.run_id).where(
                SimulationRun.status.in_({"completed", "failed"})
            )
            run_ids = [row[0] for row in session.execute(stmt).all()]
        finally:
            session.close()
    
    result: dict[str, list[EvaluationPoint]] = {}
    for run_id in run_ids:
        evaluations = parse_evaluation_logs(run_id, log_dir)
        if evaluations:
            result[run_id] = evaluations
    
    return result


def export_evaluations_to_csv(
    run_ids: list[str] | None = None,
    log_dir: str = "logs",
    include_server_stats: bool = False,
) -> tuple[str, int]:
    """
    Export evaluation data to CSV format.
    
    Args:
        run_ids: Specific run IDs to export. If None, exports all terminal runs.
        log_dir: Directory containing log files
        include_server_stats: If True, include server_stats as JSON column
    
    Returns:
        Tuple of (CSV content as string, total rows)
    """
    import csv
    import io
    
    all_evaluations = get_all_run_evaluations(run_ids, log_dir)
    
    # Collect all points across runs
    all_points: list[EvaluationPoint] = []
    for points in all_evaluations.values():
        all_points.extend(points)
    
    # Sort by timestamp
    all_points.sort(key=lambda p: p.timestamp)
    
    # Build CSV
    fieldnames = [
        "run_id",
        "timestamp",
        "virtual_time",
        "round",
        "accuracy",
        "loss",
        "architecture",
        "graph_id",
    ]
    if include_server_stats:
        fieldnames.append("server_stats_json")
    
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    
    for point in all_points:
        row = point.to_dict()
        if include_server_stats:
            row["server_stats_json"] = json.dumps(point.server_stats, default=str)
        writer.writerow(row)
    
    csv_content = buffer.getvalue()
    buffer.close()
    
    return csv_content, len(all_points)


def export_run_evaluations_to_csv(
    run_id: str,
    log_dir: str = "logs",
    include_server_stats: bool = False,
) -> tuple[str, int] | None:
    """
    Export evaluation data for a single run to CSV.
    
    Args:
        run_id: The simulation run ID
        log_dir: Directory containing log files
        include_server_stats: If True, include server_stats as JSON column
    
    Returns:
        Tuple of (CSV content, row count) or None if no data found
    """
    evaluations = parse_evaluation_logs(run_id, log_dir)
    
    if not evaluations:
        logger.warning(f"No evaluation data found for run {run_id}")
        return None
    
    # Sort by timestamp
    evaluations.sort(key=lambda p: p.timestamp)
    
    # Build CSV
    fieldnames = [
        "run_id",
        "timestamp",
        "virtual_time",
        "round",
        "accuracy",
        "loss",
        "architecture",
        "graph_id",
    ]
    if include_server_stats:
        fieldnames.append("server_stats_json")
    
    import csv
    import io
    
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    
    for point in evaluations:
        row = point.to_dict()
        if include_server_stats:
            row["server_stats_json"] = json.dumps(point.server_stats, default=str)
        writer.writerow(row)
    
    csv_content = buffer.getvalue()
    buffer.close()
    
    return csv_content, len(evaluations)
