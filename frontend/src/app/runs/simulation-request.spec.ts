import { toStartRequest } from './simulation-request';

describe('toStartRequest', () => {
  const trainingConfig = { epochs: 2, lr: 0.01, modelComplexity: 1, batchSize: 16 };
  const simulationSettings = {
    runTimeLimit: 100, evalInterval: 10, gpuBudget: 0, dataset: 'cifar10',
    seedSet: [1, 2], repetitions: 2, outputFilename: '', evaluateModel: false,
  };

  it('maps a hierarchical run without spyker settings', () => {
    const request = toStartRequest(3, { trainingConfig, simulationSettings });
    expect(request).toMatchObject({
      graph_id: 3,
      training_config: { epochs: 2, lr: 0.01, model_complexity: 1, batch_size: 16 },
      simulation_settings: { run_time_limit: 100, seed_set: [1, 2], output_filename: null, idle_token_delay: undefined },
      spyker_config: undefined,
    });
  });

  it('includes spyker specific settings', () => {
    const request = toStartRequest(4, {
      trainingConfig,
      simulationSettings: { ...simulationSettings, idleTokenDelay: 0.5, outputFilename: 'model.pth' },
      spykerConfig: { decayBeta: 0.1, minLearningRate: 1e-6, hInter: 5, hIntra: 50, sigmoidPhi: 1, serverLearningRate: 0.1, tcpRtoDelay: 0.2 },
    });
    expect(request.simulation_settings).toMatchObject({ idle_token_delay: 0.5, output_filename: 'model.pth' });
    expect(request.spyker_config).toMatchObject({ h_inter: 5, tcp_rto_delay: 0.2 });
  });
});
