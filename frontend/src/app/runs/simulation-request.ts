import { SimulationStartRequest } from '../api/graph-api.service';
import { Architecture } from '../domain/topology';
import { OptionRequestFields } from './run-options';

export type SimulationMode = Architecture | 'both';

export interface TrainingConfig {
  epochs: number;
  lr: number;
  modelComplexity: number;
  batchSize?: number;
}

export interface SimulationSettings {
  runTimeLimit: number;
  evalInterval: number;
  gpuBudget: number;
  dataset: string;
  seedSet: number[];
  repetitions: number;
  outputFilename: string;
  evaluateModel: boolean;
  /** Spyker only. */
  idleTokenDelay?: number;
}

export type DecayMode = 'absolute' | 'relative';
export type StalenessMode = 'reciprocal' | 'none' | 'delta' | 'relative';

export interface SpykerConfig {
  decayBeta: number;
  decayMode?: DecayMode;
  stalenessMode?: StalenessMode;
  minLearningRate: number;
  hInter: number | 'auto';
  hIntra: number;
  sigmoidPhi: number;
  serverLearningRate: number;
}

/** Everything needed to simulate one architecture. */
export interface ArchitectureRunConfig {
  trainingConfig: TrainingConfig;
  simulationSettings: SimulationSettings;
  /** Spyker only. */
  spykerConfig?: SpykerConfig;
  /** Optional controls from run-options.ts, already split into their request blocks. */
  options?: OptionRequestFields;
}

/** What the start dialog asks the app to run. */
export interface SimulationRequest {
  mode: SimulationMode;
  hierfl: ArchitectureRunConfig;
  spyker: ArchitectureRunConfig & {
    simulationSettings: SimulationSettings & { idleTokenDelay: number };
    spykerConfig: SpykerConfig;
  };
}

/** Maps the editor's run configuration to the backend request body. */
export function toStartRequest(graphId: number, config: ArchitectureRunConfig): SimulationStartRequest {
  const { trainingConfig: training, simulationSettings: settings, spykerConfig: spyker } = config;
  return {
    graph_id: graphId,
    training_config: {
      epochs: training.epochs,
      lr: training.lr,
      model_complexity: training.modelComplexity,
      batch_size: training.batchSize,
    },
    simulation_settings: {
      run_time_limit: settings.runTimeLimit,
      eval_interval: settings.evalInterval,
      gpu_budget: settings.gpuBudget,
      dataset: settings.dataset,
      idle_token_delay: settings.idleTokenDelay,
      seed_set: settings.seedSet,
      repetitions: settings.repetitions,
      output_filename: settings.outputFilename || null,
      evaluate_model: settings.evaluateModel,
      ...config.options?.simulation_settings,
    },
    spyker_config: spyker && {
      ...config.options?.spyker_config,
      decay_beta: spyker.decayBeta,
      decay_mode: spyker.decayMode,
      staleness_mode: spyker.stalenessMode,
      min_learning_rate: spyker.minLearningRate,
      h_inter: spyker.hInter,
      h_intra: spyker.hIntra,
      sigmoid_phi: spyker.sigmoidPhi,
      server_learning_rate: spyker.serverLearningRate,
    },
  };
}
