import { formatRunProgress } from './run-progress';

describe('formatRunProgress', () => {
  it.each([
    [{ current_sim_time: 50, run_time_limit: 200 }, '25.0%'],
    [{ current_sim_time: 500, run_time_limit: 200 }, '100.0%'],
    [{ current_sim_time: null, run_time_limit: 200 }, '-'],
    [{ current_sim_time: 5, run_time_limit: 0 }, '-'],
  ])('formats %o as %s', (run, expected) => {
    expect(formatRunProgress(run)).toBe(expected);
  });
});
