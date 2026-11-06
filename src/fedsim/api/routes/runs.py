"""API endpoints for simulation run management."""

import logging

from fastapi import APIRouter, HTTPException, Response, status

from fedsim.services.loki_sync_service import (
    fetch_run_logs,
    reconstruct_from_loki,
    sync_run_to_loki,
)

router = APIRouter(prefix="/runs", tags=["runs"])
logger = logging.getLogger(__name__)


@router.post("/{run_id}/sync-to-loki")
def sync_run_loki(run_id: str) -> dict[str, str]:
    """
    Sync evaluation points for a completed run from database to Loki.

    This endpoint is typically called when a simulation run completes,
    to persist the evaluation data in Loki for historical querying.

    Args:
        run_id: The simulation run ID

    Returns:
        Status message

    Raises:
        500: If sync to Loki fails
    """
    success = sync_run_to_loki(run_id)

    if not success:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to sync run {run_id} to Loki",
        )

    return {"status": "ok", "run_id": run_id, "message": "Evaluation points synced to Loki"}


@router.post("/{run_id}/reconstruct-from-loki")
def reconstruct_run_loki(run_id: str) -> dict[str, str]:
    """
    Reconstruct evaluation points from Loki logs into the database.

    Useful after container restart when database is empty but Loki still has logs.
    Queries Loki for evaluation logs and backfills them into the database.

    Args:
        run_id: The simulation run ID

    Returns:
        Status message with number of points reconstructed
    """
    count = reconstruct_from_loki(run_id)

    if count == 0:
        logger.info("reconstruct_run_loki no data found run_id=%s", run_id)
        return {
            "status": "ok",
            "run_id": run_id,
            "message": "No logs found in Loki to reconstruct",
            "reconstructed": "0",
        }

    logger.info("reconstruct_run_loki success run_id=%s count=%d", run_id, count)
    return {
        "status": "ok",
        "run_id": run_id,
        "message": f"Reconstructed {count} evaluation points from Loki",
        "reconstructed": str(count),
    }


@router.get("/{run_id}/logs")
def get_run_logs(run_id: str) -> Response:
    """
    Return the raw periodic evaluator logs for a run.

    Prefers the persisted `raw_logs` column and falls back to Loki if needed.
    """
    logs = fetch_run_logs(run_id)
    if not logs:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"No logs found for run {run_id}"
        )

    return Response(
        content=logs,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'inline; filename="run_{run_id}_logs.txt"'},
    )
