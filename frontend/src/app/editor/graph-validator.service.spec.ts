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
});
