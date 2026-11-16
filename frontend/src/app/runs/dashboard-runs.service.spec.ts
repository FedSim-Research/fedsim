import { HttpErrorResponse } from '@angular/common/http';
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

  it('does not raise loading for background polls but does for explicit loads', async () => {
    const service = TestBed.inject(DashboardRunsService);
    service.startPolling();
    expect(service.loading()).toBe(true);
    await vi.advanceTimersByTimeAsync(0);
    expect(service.loading()).toBe(false);

    let finish!: (runs: []) => void;
    listRuns.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    await vi.advanceTimersByTimeAsync(4000);
    expect(listRuns).toHaveBeenCalledTimes(2);
    expect(service.loading()).toBe(false);

    const explicit = service.refreshRuns(); // joins the background request
    expect(service.loading()).toBe(true);
    finish([]);
    await explicit;
    expect(service.loading()).toBe(false);

    listRuns.mockImplementationOnce(() => new Promise((resolve) => { finish = resolve; }));
    const again = service.refreshRuns();
    expect(service.loading()).toBe(true);
    finish([]);
    await again;
    service.stopPolling();
  });

  describe('when /runs returns 404', () => {
    const notFound = () => new HttpErrorResponse({ status: 404 });

    it('stops the interval and resumes on retry while a consumer is active', async () => {
      listRuns.mockRejectedValueOnce(notFound());
      const service = TestBed.inject(DashboardRunsService);
      service.startPolling();
      await vi.advanceTimersByTimeAsync(12000);
      expect(service.pollingSupported()).toBe(false);
      expect(listRuns).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);

      await service.retryRunTracking();
      expect(listRuns).toHaveBeenCalledTimes(2);
      await vi.advanceTimersByTimeAsync(4000);
      expect(listRuns).toHaveBeenCalledTimes(3);
      service.stopPolling();
      expect(vi.getTimerCount()).toBe(0);
    });

    it('does not start an interval on retry without consumers', async () => {
      listRuns.mockRejectedValueOnce(notFound());
      const service = TestBed.inject(DashboardRunsService);
      service.startPolling();
      await vi.advanceTimersByTimeAsync(0);
      service.stopPolling();
      await service.retryRunTracking();
      expect(service.pollingSupported()).toBe(true);
      expect(vi.getTimerCount()).toBe(0);
    });

    it('leaves no interval when the last consumer stops during the pause', async () => {
      listRuns.mockRejectedValueOnce(notFound());
      const service = TestBed.inject(DashboardRunsService);
      service.startPolling();
      await vi.advanceTimersByTimeAsync(0);
      service.stopPolling();
      expect(vi.getTimerCount()).toBe(0);
    });
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
