import { TestBed } from '@angular/core/testing';
import { MessageService } from 'primeng/api';
import { GraphApiService } from '../api/graph-api.service';
import { GraphValidatorService } from '../editor/graph-validator.service';
import { GraphWorkspace } from '../editor/graph-workspace.service';
import { formatSimulationResult, SimulationRunner } from './simulation-runner.service';
import { SimulationRequest } from './simulation-request';

describe('SimulationRunner', () => {
  const api = { startSimulation: vi.fn(), startSimulationBoth: vi.fn(), getRunStatus: vi.fn() };
  const add = vi.fn();
  const validate = vi.fn();
  const graph = () => ({ getGraphId: () => 9, loadGraphIdFromStorage: () => null, nodes: () => [], edges: () => [], flushSave: vi.fn().mockResolvedValue(undefined) });
  const hierfl = graph();

  const settings = {
    runTimeLimit: 1, evalInterval: 0, gpuBudget: 0, dataset: 'd', seedSet: [1],
    repetitions: 1, outputFilename: '', evaluateModel: false,
  };
  const request = {
    mode: 'hierfl',
    hierfl: { trainingConfig: { epochs: 1, lr: 0.1, modelComplexity: 1 }, simulationSettings: settings },
    spyker: {},
  } as unknown as SimulationRequest;

  beforeEach(() => {
    vi.useFakeTimers();
    Object.values(api).forEach((mock) => mock.mockReset());
    add.mockReset();
    validate.mockReset().mockReturnValue([]);
    TestBed.configureTestingModule({
      providers: [
        { provide: GraphApiService, useValue: api },
        { provide: MessageService, useValue: { add } },
        { provide: GraphValidatorService, useValue: { validateSimulationRequest: validate } },
        { provide: GraphWorkspace, useValue: { graphFor: () => hierfl } },
      ],
    });
  });

  afterEach(() => vi.useRealTimers());

  it('saves the graph before starting and reports the result', async () => {
    api.startSimulation.mockResolvedValue({ run_id: 'r1', status: 'queued' });
    api.getRunStatus
      .mockRejectedValueOnce(new Error('blip'))
      .mockResolvedValueOnce({ run_id: 'r1', status: 'completed', repetitions: 1 });

    const done = TestBed.inject(SimulationRunner).run(request);
    await vi.runAllTimersAsync();
    await done;

    expect(hierfl.flushSave).toHaveBeenCalled();
    expect(api.startSimulation).toHaveBeenCalledWith(expect.objectContaining({ graph_id: 9 }));
    expect(add).toHaveBeenLastCalledWith(expect.objectContaining({ severity: 'success', detail: 'hierfl: Completed' }));
  });

  it('does not start an invalid simulation', async () => {
    validate.mockReturnValue(['hierfl: graph must contain at least one Client']);
    await TestBed.inject(SimulationRunner).run(request);

    expect(api.startSimulation).not.toHaveBeenCalled();
    expect(add).toHaveBeenCalledWith(expect.objectContaining({ summary: 'hierfl validation failed' }));
  });

  it('does not submit a simulation if its latest graph could not be saved', async () => {
    hierfl.flushSave.mockRejectedValueOnce(new Error('save failed'));

    await expect(TestBed.inject(SimulationRunner).run(request)).resolves.toBeUndefined();

    expect(api.startSimulation).not.toHaveBeenCalled();
    expect(add).toHaveBeenCalledWith(expect.objectContaining({
      severity: 'error',
      detail: expect.stringContaining('save'),
    }));
  });
});

describe('formatSimulationResult', () => {
  it('summarises evaluated repetitions', () => {
    expect(formatSimulationResult('spyker', {
      repetitions: 3,
      evaluation_summary: { evaluated_repetitions: 3, mean_accuracy: 0.5, variance_accuracy: 0.01, mean_avg_loss: 1.2, variance_avg_loss: 0.1 },
    })).toBe('spyker: 3 repetitions completed, Mean accuracy 50.00%, Accuracy variance 0.010000, Mean loss 1.2000, Loss variance 0.100000');
  });
});
