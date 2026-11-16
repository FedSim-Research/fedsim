import { StaticEdge, StaticNode } from 'ngx-vflow';
import { GraphValidatorService } from './graph-validator.service';

describe('Spyker topology validation', () => {
  const validator = new GraphValidatorService();
  const config = {
    trainingConfig: { epochs: 1, lr: 0.01, modelComplexity: 1 },
    simulationSettings: {
      runTimeLimit: 10, evalInterval: 0, gpuBudget: 0, dataset: 'uoft-cs/cifar10',
      seedSet: [17], repetitions: 1, outputFilename: '', evaluateModel: false,
      idleTokenDelay: 1,
    },
  };

  function node(id: string, type: string): StaticNode {
    return {
      id, type: 'html-template', point: { x: 0, y: 0 },
      data: { type, config: { computeFactor: 10, uploadMbps: 100, downloadMbps: 100, count: 1 } },
    };
  }

  function edge(source: string, target: string): StaticEdge {
    return {
      id: `${source}-${target}`, source, target,
      data: { metrics: { pingMs: 0, jitterMs: 0, packetloss: 0, packetlossStddev: 0 } },
    };
  }

  it.each([1, 2, 3])('accepts a complete topology with %i servers', (count) => {
    const servers = ['A', 'B', 'C'].slice(0, count);
    const nodes = [...servers.map((id) => node(id, 'ServerNode')), node('client', 'ClientNode')];
    const edges = [edge('client', 'A')];
    for (let i = 0; i < servers.length; i++) {
      for (let j = i + 1; j < servers.length; j++) {
        edges.push(edge(servers[j], servers[i]));
      }
    }
    expect(validator.validateSimulationRequest('spyker', nodes, edges, config)).toEqual([]);
  });

  it.each([false, true])('rejects missing server links (connected path: %s)', (connected) => {
    const nodes = ['A', 'B', 'C'].map((id) => node(id, 'ServerNode'));
    nodes.push(node('client', 'ClientNode'));
    const edges = [edge('client', 'A'), edge('A', 'B')];
    if (connected) edges.push(edge('B', 'C'));
    expect(validator.validateSimulationRequest('spyker', nodes, edges, config)).toContain(
      'spyker: each Server must be directly connected to every other Server',
    );
  });

  it.each([
    ['uploadMbps', 0, 'upload'],
    ['downloadMbps', 0, 'download'],
    ['uploadMbps', Number.NaN, 'upload'],
    ['downloadMbps', Number.POSITIVE_INFINITY, 'download'],
    ['uploadMbps', true, 'upload'],
    ['count', 1.5, 'count'],
    ['count', true, 'count'],
  ])('rejects invalid node control %s = %s', (field, value, keyword) => {
    const nodes = [node('A', 'ServerNode'), node('client', 'ClientNode')];
    (nodes[1] as any).data.config[field as string] = value;
    const errors = validator.validateSimulationRequest('spyker', nodes, [edge('client', 'A')], config);
    expect(errors.some((error) => error.toLowerCase().includes(keyword as string))).toBe(true);
  });

  it.each(['hInter', 'hIntra'])('rejects fractional %s thresholds', (field) => {
    const spykerConfig = {
      decayBeta: 0.05, minLearningRate: 1e-6, hInter: 5, hIntra: 350,
      sigmoidPhi: 1.5, serverLearningRate: 0.6, [field]: 1.5,
    };
    const errors = validator.validateSimulationRequest('spyker',
      [node('A', 'ServerNode'), node('client', 'ClientNode')], [edge('client', 'A')],
      { ...config, spykerConfig });
    expect(errors.some((error) => error.toLowerCase().includes(field.toLowerCase()))).toBe(true);
  });

  it.each([['auto', false], ['fast', true]])('validates hInter %s (rejected: %s)', (hInter, rejected) => {
    const spykerConfig = {
      decayBeta: 0.05, minLearningRate: 1e-6, hInter, hIntra: 350,
      sigmoidPhi: 1.5, serverLearningRate: 0.6,
    } as any;
    const errors = validator.validateSimulationRequest('spyker',
      [node('A', 'ServerNode'), node('client', 'ClientNode')], [edge('client', 'A')],
      { ...config, spykerConfig });
    expect(errors.some((error) => error.includes('hInter'))).toBe(rejected);
  });

  it('rejects fractional local epochs', () => {
    const errors = validator.validateSimulationRequest('spyker',
      [node('A', 'ServerNode'), node('client', 'ClientNode')], [edge('client', 'A')],
      { ...config, trainingConfig: { ...config.trainingConfig, epochs: 1.5 } });
    expect(errors.some((error) => error.includes('epochs'))).toBe(true);
  });

  it('rejects a hierarchical Server without Clients', () => {
    const nodes = [
      node('S', 'SuperServerNode'), node('A', 'ServerNode'), node('idle', 'ServerNode'),
      node('client', 'ClientNode'),
    ];
    const edges = [edge('A', 'S'), edge('idle', 'S'), edge('client', 'A')];
    expect(validator.validateSimulationRequest('hierfl', nodes, edges, config)).toContain(
      'hierfl: each Server must have at least one Client',
    );
  });

  it.each([['pingMs', null, 'ping'], ['packetloss', false, 'packetloss']])(
    'rejects nonnumeric edge control %s', (field, value, keyword) => {
      const link = edge('client', 'A');
      (link as any).data.metrics[field as string] = value;
      const errors = validator.validateSimulationRequest('spyker',
        [node('A', 'ServerNode'), node('client', 'ClientNode')], [link], config);
      expect(errors.some((error) => error.includes(keyword as string))).toBe(true);
    },
  );
});
