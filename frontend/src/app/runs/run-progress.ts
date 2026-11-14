import { SimulationRunResponse } from '../api/graph-api.service';

/** Simulated time as a share of the run's time limit, in percent; null when unknown. */
export function runProgressPercent(run: Pick<SimulationRunResponse, 'current_sim_time' | 'run_time_limit'>): number | null {
  const current = Number(run.current_sim_time ?? Number.NaN);
  const limit = Number(run.run_time_limit ?? Number.NaN);
  if (!Number.isFinite(current) || !Number.isFinite(limit) || limit <= 0) {
    return null;
  }
  return Math.max(0, Math.min(100, (current / limit) * 100));
}

export function formatRunProgress(run: Pick<SimulationRunResponse, 'current_sim_time' | 'run_time_limit'>): string {
  const progress = runProgressPercent(run);
  return progress === null ? '-' : `${progress.toFixed(1)}%`;
}
