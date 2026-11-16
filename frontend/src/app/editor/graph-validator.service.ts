import { Injectable } from '@angular/core';
import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { Architecture } from '../domain/topology';
import { canLink } from '../domain/link-rules';
import { ArchitectureRunConfig } from '../runs/simulation-request';
import { validateOptionValues } from '../runs/run-options';

type FlowNodeData = { type?: string; config?: Record<string, unknown> };
type FlowEdgeMetrics = {
  pingMs?: number;
  jitterMs?: number;
  packetloss?: number;
  packetlossStddev?: number;
};

@Injectable({
  providedIn: 'root',
})
export class GraphValidatorService {
  public validateSimulationRequest(
    architecture: Architecture,
    nodes: Node[],
    edges: Edge[],
    config: ArchitectureRunConfig,
  ): string[] {
    const errors: string[] = [];
    errors.push(...this.validateTrainingAndSimulationFields(architecture, config));
    errors.push(...this.validateGraph(architecture, nodes, edges));
    return errors;
  }

  private validateTrainingAndSimulationFields(
    architecture: Architecture,
    config: ArchitectureRunConfig,
  ): string[] {
    const errors: string[] = [];
    if (!Number.isInteger(config.trainingConfig.epochs) || config.trainingConfig.epochs < 1) {
      errors.push(`${architecture}: epochs must be an integer >= 1`);
    }
    if (!Number.isFinite(config.trainingConfig.lr) || config.trainingConfig.lr <= 0) {
      errors.push(`${architecture}: learning rate must be > 0`);
    }
    if (!Number.isFinite(config.trainingConfig.modelComplexity) || config.trainingConfig.modelComplexity <= 0) {
      errors.push(`${architecture}: model complexity must be > 0`);
    }
    if (
      config.trainingConfig.batchSize !== undefined
      && (!Number.isInteger(config.trainingConfig.batchSize) || config.trainingConfig.batchSize < 1)
    ) {
      errors.push(`${architecture}: batch size must be an integer >= 1`);
    }
    if (!Number.isFinite(config.simulationSettings.runTimeLimit) || config.simulationSettings.runTimeLimit <= 0) {
      errors.push(`${architecture}: run time limit must be > 0`);
    }
    if (!Number.isFinite(config.simulationSettings.evalInterval) || config.simulationSettings.evalInterval < 0) {
      errors.push(`${architecture}: eval interval must be >= 0`);
    }
    if (!Number.isFinite(config.simulationSettings.gpuBudget) || config.simulationSettings.gpuBudget < 0) {
      errors.push(`${architecture}: gpu budget must be >= 0`);
    }
    if (typeof config.simulationSettings.dataset !== 'string' || config.simulationSettings.dataset.trim().length === 0) {
      errors.push(`${architecture}: dataset must be a non-empty dataset id`);
    }
    const seedSet = config.simulationSettings.seedSet;
    if (!Array.isArray(seedSet) || seedSet.length === 0) {
      errors.push(`${architecture}: seed set must contain at least one integer seed`);
    } else {
      for (const seed of seedSet) {
        if (!Number.isInteger(seed) || seed < 0) {
          errors.push(`${architecture}: seed set entries must be integers >= 0`);
          break;
        }
      }
    }
    if (!Number.isInteger(config.simulationSettings.repetitions) || config.simulationSettings.repetitions < 1) {
      errors.push(`${architecture}: repetitions must be an integer >= 1`);
    } else if (Array.isArray(seedSet) && seedSet.length > 0 && config.simulationSettings.repetitions !== seedSet.length) {
      errors.push(`${architecture}: repetitions must match the number of seeds in the seed set`);
    }
    if (config.simulationSettings.evaluateModel && !config.simulationSettings.outputFilename?.trim()) {
      errors.push(`${architecture}: output filename is required for evaluation`);
    }
    if (
      architecture === 'spyker' &&
      (config.simulationSettings.idleTokenDelay === undefined ||
        !Number.isFinite(config.simulationSettings.idleTokenDelay) ||
        config.simulationSettings.idleTokenDelay < 0)
    ) {
      errors.push('spyker: idle token delay must be >= 0');
    }
    if (architecture === 'spyker' && config.spykerConfig) {
      const s = config.spykerConfig;
      if (!Number.isFinite(s.decayBeta) || s.decayBeta < 0) errors.push('spyker: decay beta must be >= 0');
      if (s.decayMode !== undefined && !['absolute', 'relative'].includes(s.decayMode)) errors.push('spyker: decayMode must be absolute or relative');
      if (s.stalenessMode !== undefined && !['reciprocal', 'none', 'delta', 'relative'].includes(s.stalenessMode)) errors.push('spyker: stalenessMode must be reciprocal, none, delta or relative');
      if (!Number.isFinite(s.minLearningRate) || s.minLearningRate <= 0) errors.push('spyker: min learning rate must be > 0');
      if (s.hInter !== 'auto' && (!Number.isInteger(s.hInter) || s.hInter < 1)) errors.push('spyker: hInter must be an integer >= 1');
      if (!Number.isInteger(s.hIntra) || s.hIntra < 1) errors.push('spyker: hIntra must be an integer >= 1');
      if (!Number.isFinite(s.sigmoidPhi) || s.sigmoidPhi <= 0) errors.push('spyker: sigmoid phi must be > 0');
      if (!Number.isFinite(s.serverLearningRate) || s.serverLearningRate <= 0) errors.push('spyker: server learning rate must be > 0');
    }
    if (config.options) {
      const values = { ...config.options.simulation_settings, ...config.options.spyker_config };
      errors.push(...validateOptionValues(architecture, values));
    }
    return errors;
  }

  private validateGraph(architecture: Architecture, nodes: Node[], edges: Edge[]): string[] {
    const errors: string[] = [];
    const nodeTypeById = new Map<string, string>();
    for (const node of nodes) {
      const nodeType = this.getNodeData(node).type;
      if (nodeType) {
        nodeTypeById.set(node.id, nodeType);
      }
      errors.push(...this.validateNodeConfig(architecture, node));
    }
    const superNodes = nodes.filter((n) => this.getNodeData(n).type === 'SuperServerNode');
    const serverNodes = nodes.filter((n) => this.getNodeData(n).type === 'ServerNode');
    const clientNodes = nodes.filter((n) => this.getNodeData(n).type === 'ClientNode');

    if (architecture === 'hierfl' && superNodes.length !== 1) {
      errors.push('hierfl: graph must contain exactly one Super Server');
    }
    if (architecture === 'spyker' && superNodes.length > 0) {
      errors.push('spyker: graph must not contain a Super Server');
    }
    if (serverNodes.length === 0) {
      errors.push(`${architecture}: graph must contain at least one Server`);
    }
    if (clientNodes.length === 0) {
      errors.push(`${architecture}: graph must contain at least one Client`);
    }

    const adjacency = new Map<string, Set<string>>();
    for (const edge of edges) {
      const sourceType = nodeTypeById.get(edge.source);
      const targetType = nodeTypeById.get(edge.target);
      if (!sourceType || !targetType) {
        errors.push(`${architecture}: edge references missing node`);
        continue;
      }
      if (!canLink(architecture, sourceType, targetType)) {
        errors.push(`${architecture}: invalid edge ${sourceType} -> ${targetType}`);
      }
      if (!adjacency.has(edge.source)) adjacency.set(edge.source, new Set<string>());
      if (!adjacency.has(edge.target)) adjacency.set(edge.target, new Set<string>());
      adjacency.get(edge.source)?.add(edge.target);
      adjacency.get(edge.target)?.add(edge.source);
      errors.push(...this.validateEdgeMetrics(architecture, edge));
    }

    const serverIds = new Set(serverNodes.map((n) => n.id));
    const superId = superNodes[0]?.id;

    if (architecture === 'spyker') {
      for (const server of serverNodes) {
        const neighbors = adjacency.get(server.id) ?? new Set<string>();
        if (serverNodes.some((peer) => peer.id !== server.id && !neighbors.has(peer.id))) {
          errors.push('spyker: each Server must be directly connected to every other Server');
          break;
        }
      }
    }

    if (architecture === 'hierfl' && superId) {
      for (const server of serverNodes) {
        const neighbors = adjacency.get(server.id) ?? new Set<string>();
        if (!neighbors.has(superId)) {
          errors.push('hierfl: each Server must be connected to the Super Server');
          break;
        }
      }
      const clientIds = new Set(clientNodes.map((n) => n.id));
      for (const server of serverNodes) {
        const neighbors = adjacency.get(server.id) ?? new Set<string>();
        if (![...neighbors].some((id) => clientIds.has(id))) {
          errors.push('hierfl: each Server must have at least one Client');
          break;
        }
      }
    }

    for (const client of clientNodes) {
      const neighbors = adjacency.get(client.id) ?? new Set<string>();
      const connectedServers = [...neighbors].filter((id) => serverIds.has(id));
      if (connectedServers.length !== 1) {
        errors.push(`${architecture}: each Client must be connected to exactly one Server`);
        break;
      }
    }
    return errors;
  }

  private validateNodeConfig(architecture: Architecture, node: Node): string[] {
    const errors: string[] = [];
    const data = this.getNodeData(node);
    const config = data.config ?? {};
    const nodeType = data.type ?? 'Node';
    const read = (key: string): number | undefined => this.finiteNumber(config[key]);

    if (nodeType !== 'SuperServerNode' || architecture === 'hierfl') {
      const computeFactor = read('computeFactor');
      const uploadMbps = read('uploadMbps');
      const downloadMbps = read('downloadMbps');
      if (computeFactor === undefined || computeFactor <= 0) errors.push(`${architecture}: ${nodeType} compute factor must be > 0`);
      if (uploadMbps === undefined || uploadMbps <= 0) errors.push(`${architecture}: ${nodeType} upload must be > 0`);
      if (downloadMbps === undefined || downloadMbps <= 0) errors.push(`${architecture}: ${nodeType} download must be > 0`);
      if (config['performanceSigma'] !== undefined && config['performanceSigma'] !== null) {
        const sigma = read('performanceSigma');
        if (sigma === undefined || sigma < 0) errors.push(`${architecture}: ${nodeType} runtime sigma must be >= 0`);
      }
    }

    if (nodeType === 'ClientNode') {
      const count = read('count');
      if (count === undefined || !Number.isInteger(count) || count < 1) errors.push(`${architecture}: Client count must be an integer >= 1`);
      if (architecture === 'hierfl') {
        const clientType = config['type'];
        if (typeof clientType !== 'string' || !clientType.trim()) {
          errors.push('hierfl: Client type is required');
        }
      }
    }
    return errors;
  }

  private validateEdgeMetrics(architecture: Architecture, edge: Edge): string[] {
    const errors: string[] = [];
    const rawMetrics = this.getEdgeMetrics(edge);
    const ping = this.finiteNumber(rawMetrics.pingMs);
    const jitter = this.finiteNumber(rawMetrics.jitterMs);
    const packetloss = this.finiteNumber(rawMetrics.packetloss);
    const packetlossStddev = this.finiteNumber(rawMetrics.packetlossStddev);

    if (ping === undefined || ping < 0) errors.push(`${architecture}: edge ping must be >= 0`);
    if (jitter === undefined || jitter < 0) errors.push(`${architecture}: edge jitter must be >= 0`);
    if (packetloss === undefined || packetloss < 0 || packetloss > 1) errors.push(`${architecture}: edge packetloss must be in [0, 1]`);
    if (packetlossStddev === undefined || packetlossStddev < 0 || packetlossStddev > 1) {
      errors.push(`${architecture}: edge packetloss stddev must be in [0, 1]`);
    }
    return errors;
  }

  private finiteNumber(value: unknown): number | undefined {
    if (typeof value !== 'number' && typeof value !== 'string') return undefined;
    if (typeof value === 'string' && !value.trim()) return undefined;
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  private getNodeData(node: Node): FlowNodeData {
    return ((node as unknown as { data?: FlowNodeData }).data ?? {});
  }

  private getEdgeMetrics(edge: Edge): FlowEdgeMetrics {
    const data = ((edge as unknown as { data?: Record<string, unknown> }).data ?? {});
    const metrics = data['metrics'] as FlowEdgeMetrics | undefined;
    return metrics ?? (data as FlowEdgeMetrics);
  }
}
