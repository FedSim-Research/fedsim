import { TestBed } from '@angular/core/testing';
import { GraphApiService, SimulationRunResponse } from '../api/graph-api.service';
import { DashboardRunsService } from './dashboard-runs.service';

describe('DashboardRunsService polling', () => {
  const listRuns = vi.fn().mockResolvedValue([]);
  const deleteRun = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    vi.useFakeTimers();
    listRuns.mockReset().mockResolvedValue([]);
    deleteRun.mockClear();
    TestBed.configureTestingModule({
      providers: [{ provide: GraphApiService, useValue: { listRuns, deleteRun } }],
    });
  });

  afterEach(() => vi.useRealTimers());

  it('keeps polling while another consumer is still active', async () => {
    const service = TestBed.inject(DashboardRunsService);
    service.startPolling();
    service.startPolling();
    service.stopPolling();
    listRuns.mockClear();

    await vi.advanceTimersByTimeAsync(4000);
    expect(listRuns).toHaveBeenCalledTimes(1);

    service.stopPolling();
    await vi.advanceTimersByTimeAsync(8000);
    expect(listRuns).toHaveBeenCalledTimes(1);
  });

  it('coalesces polls while a slow request is still in flight', async () => {
    let finish!: (runs: []) => void;
    listRuns.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const service = TestBed.inject(DashboardRunsService);
    service.startPolling();
    await vi.advanceTimersByTimeAsync(12000);
    expect(listRuns).toHaveBeenCalledTimes(1);
    finish([]);
    await vi.advanceTimersByTimeAsync(4000);
    expect(listRuns).toHaveBeenCalledTimes(2);
    service.stopPolling();
  });

  it('fetches fresh results after deletion even when an older poll is pending', async () => {
    let finish!: (runs: []) => void;
    listRuns.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const service = TestBed.inject(DashboardRunsService);
    const refresh = service.refreshRuns();
    const deleted = service.deleteRun('old-run');
    await Promise.resolve();
    expect(listRuns).toHaveBeenCalledTimes(1);
    finish([]);
    await Promise.all([refresh, deleted]);
    expect(deleteRun).toHaveBeenCalledWith('old-run');
    expect(listRuns).toHaveBeenCalledTimes(2);
  });
});

describe('DashboardRunsService architecture filter', () => {
  it('matches backend architecture names through one resolution', () => {
    TestBed.configureTestingModule({ providers: [{ provide: GraphApiService, useValue: {} }] });
    const service = TestBed.inject(DashboardRunsService);
    service.runs.set(['hierarchical', 'hierfl', 'spyker', 'p2p'].map((architecture, index) => ({
      run_id: `run-${index}`, status: 'completed', architecture,
    })) as unknown as SimulationRunResponse[]);
    const architectures = () => service.filteredRuns().map((run) => String(run.architecture));

    service.filterArchitecture.set('hierfl');
    expect(architectures()).toEqual(['hierarchical', 'hierfl']);
    service.filterArchitecture.set('spyker');
    expect(architectures()).toEqual(['spyker']);
    service.filterArchitecture.set('all');
    expect(architectures()).toHaveLength(4);
  });
});
