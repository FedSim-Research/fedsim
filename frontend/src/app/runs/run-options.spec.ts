import {
  RUN_OPTIONS,
  defaultOptionValues,
  optionRequestFields,
  validateOptionValues,
} from './run-options';
import { toStartRequest } from './simulation-request';

describe('run options', () => {
  it('defaults leave every optional control unset or at the backend default', () => {
    const values = defaultOptionValues('spyker');
    expect(values['sync_timeout']).toBeNull();
    expect(values['fifo_links']).toBe(false);
    expect(Object.keys(values)).toEqual(RUN_OPTIONS.spyker.map((o) => o.requestKey));
  });

  it('routes values into their request blocks and omits unset ones', () => {
    const values = { ...defaultOptionValues('spyker'), fifo_links: true, labels_per_client: null };
    const fields = optionRequestFields('spyker', values);
    expect(fields.spyker_config['fifo_links']).toBe(true);
    expect(fields.simulation_settings['partitioning']).toBe('iid');
    expect('labels_per_client' in fields.simulation_settings).toBe(false);
  });

  it.each([
    [{ partitioning: 'label-skew', labels_per_client: null }, 'requires labels'],
    [{ local_holdout: 1 }, 'Local holdout'],
    [{ edge_rounds: 1.5 }, 'Edge rounds'],
    [{ partitioning: 'dirichlet' }, 'Data partitioning'],
  ])('rejects invalid values %o', (override, message) => {
    const values = { ...defaultOptionValues('hierfl'), ...override };
    expect(validateOptionValues('hierfl', values).some((e) => e.includes(message))).toBe(true);
  });

  it('accepts the defaults', () => {
    expect(validateOptionValues('hierfl', defaultOptionValues('hierfl'))).toEqual([]);
    expect(validateOptionValues('spyker', defaultOptionValues('spyker'))).toEqual([]);
  });

  it.each(['hierfl', 'spyker'] as const)('requires a separate response throughput for %s', (architecture) => {
    const values = { ...defaultOptionValues(architecture), aggregation_delay: true };
    expect(validateOptionValues(architecture, values).some((e) => e.includes('requires aggregation throughput'))).toBe(true);
    expect(validateOptionValues(architecture, { ...values, aggregation_bytes_per_second: 100_000_000 })).toEqual([]);
    expect(validateOptionValues(architecture, { ...values, aggregation_bytes_per_second: 0 }).length).toBeGreaterThan(0);
  });

  it.each(['hierfl', 'spyker'] as const)('routes ordering and response throughput for %s', (architecture) => {
    const fields = optionRequestFields(architecture, {
      ...defaultOptionValues(architecture), event_order: 'parent',
      aggregation_delay: true, aggregation_bytes_per_second: 100_000_000,
    });
    expect(fields.simulation_settings['event_order']).toBe('parent');
    const settings = architecture === 'hierfl' ? fields.simulation_settings : fields.spyker_config;
    expect(settings['aggregation_delay']).toBe(true);
    expect(settings['aggregation_bytes_per_second']).toBe(100_000_000);
  });

  it('merges options into the start request', () => {
    const request = toStartRequest(1, {
      trainingConfig: { epochs: 1, lr: 0.01, modelComplexity: 1 },
      simulationSettings: {
        runTimeLimit: 10, evalInterval: 0, gpuBudget: 0, dataset: 'uoft-cs/cifar10',
        seedSet: [1], repetitions: 1, outputFilename: '', evaluateModel: false,
      },
      options: optionRequestFields('hierfl', { ...defaultOptionValues('hierfl'), edge_rounds: 3 }),
    });
    expect(request.simulation_settings?.['edge_rounds']).toBe(3);
    expect(request.spyker_config).toBeUndefined();
  });
});
