"""API endpoints for simulation run management."""

import logging
from fastapi import APIRouter, HTTPException, status

from backend.services.loki_sync_service import sync_run_to_loki
from backend.services.loki_sync_service import sync_run_to_loki, reconstruct_from_loki

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
            detail=f"Failed to sync run {run_id} to Loki"
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
        return {"status": "ok", "run_id": run_id, "message": "No logs found in Loki to reconstruct", "reconstructed": "0"}
    
    logger.info("reconstruct_run_loki success run_id=%s count=%d", run_id, count)
    return {"status": "ok", "run_id": run_id, "message": f"Reconstructed {count} evaluation points from Loki", "reconstructed": str(count)}
