import { Injectable, inject } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge } from 'ngx-vflow';
import { GraphApiService, GraphDetail, VflowGraph } from '../api/graph-api.service';
import { GraphService } from './graph.service';
import { ClientNode } from './nodes/client-node/client-node';
import { ServerNode } from './nodes/server-node/server-node';
import { SuperServerNode } from './nodes/super-server-node/super-server-node';
import { EdgeMetrics, EDGE_METRIC_DEFAULTS } from '../api/edge-metrics';
import { State } from './graph-history.service';

const NODE_TYPE_MAP = {
  ClientNode: ClientNode,
  ServerNode: ServerNode,
  SuperServerNode: SuperServerNode,
} as const;

type Architecture = 'spyker' | 'hierfl';

@Injectable({ providedIn: 'root' })
export class GraphPersistenceService {
  private api = inject(GraphApiService);

  public async initializeGraph(
    service: GraphService<any>,
    architecture: Architecture,
    createIfMissing: boolean = true
  ): Promise<void> {
    const storedId = service.loadGraphIdFromStorage();
    if (storedId !== null) {
      const loaded = await this.tryLoadGraph(service, architecture, storedId);
      if (loaded) {
        return;
      }
    }

    if (!createIfMissing) {
      service.setGraphId(null);
      service.setGraphState([], [], true);
      return;
    }

    const created = await this.api.createGraph({
      name: `${architecture}-graph`,
      architecture,
      metadata: null,
    });
    service.setGraphId(created.graph_id);
    service.setGraphState([], [], true);
  }

  private async tryLoadGraph(
    service: GraphService<any>,
    architecture: Architecture,
    graphId: number
  ): Promise<boolean> {
    try {
      const graph = await this.api.getGraph(graphId);
      this.applyGraph(service, architecture, graph);
      service.setGraphId(graphId);
      return true;
    } catch {
      return false;
    }
  }

  private applyGraph(service: GraphService<any>, architecture: Architecture, graph: GraphDetail): void {
    const snapshot = this.toStateSnapshot(architecture, graph);
    service.setGraphState(snapshot.nodes, snapshot.edges, true);
  }

  private reconcileGraph(service: GraphService<any>, architecture: Architecture, graph: GraphDetail): void {
    const backendSnapshot = this.toStateSnapshot(architecture, graph);
    const mergedSnapshot = this.mergeBackendState(service, backendSnapshot);
    service.applyHistoryState(mergedSnapshot);
    service.getGraphHistory().replaceCurrentState({
      nodes: service.nodes(),
      edges: service.edges(),
    });
  }

  private toStateSnapshot(architecture: Architecture, graph: GraphDetail): State {
    const nodes: Node[] = [];
    const externalByBackendId = new Map<string, string>();

    for (const node of graph.nodes) {
      const nodeType = NODE_TYPE_MAP[node.type as keyof typeof NODE_TYPE_MAP];
      if (!nodeType) {
        continue;
      }
      externalByBackendId.set(node.node_id, node.node_id);
      nodes.push({
        id: node.node_id,
        point: node.position,
        type: nodeType,
        data: {
          type: node.type,
          config: node.config,
          environment: architecture,
          fromJson: true,
          selected: false,
          backendId: node.node_id,
        },
      });
    }

    const edges: Edge[] = [];
    for (const edge of graph.edges) {
      const source = externalByBackendId.get(edge.source_node_id);
      const target = externalByBackendId.get(edge.target_node_id);
      if (!source || !target) {
        continue;
      }
      edges.push({
        id: `${edge.edge_id}`,
        source,
        target,
        reconnectable: true,
        floating: false,
        data: {
          backendId: edge.edge_id,
          metrics: edge.config ?? EDGE_METRIC_DEFAULTS,
        },
      });
    }

    return { nodes, edges };
  }

  private mergeBackendState(service: GraphService<any>, backendSnapshot: State): State {
    const backendNodes = new Map(
      backendSnapshot.nodes.map((node) => [node.id, node] as const)
    );
    const backendEdges = new Map(
      backendSnapshot.edges.map((edge) => [`${edge.source}->${edge.target}`, edge] as const)
    );

    const nodes = service.nodes().map((node) => {
      const backendNode = backendNodes.get(node.id);
      if (!backendNode) {
        return node;
      }
      const currentData = (node as any).data ?? {};
      const backendData = (backendNode as any).data ?? {};
      return {
        ...node,
        data: {
          ...currentData,
          ...backendData,
          config: backendData.config ?? currentData.config ?? {},
          selected: currentData.selected ?? false,
        },
      } as Node;
    });

    const edges = service.edges().map((edge) => {
      const backendEdge = backendEdges.get(`${edge.source}->${edge.target}`);
      if (!backendEdge) {
        return edge;
      }
      const currentData = (edge as any).data ?? {};
      const backendData = (backendEdge as any).data ?? {};
      return {
        ...edge,
        data: {
          ...currentData,
          ...backendData,
          metrics: backendData.metrics ?? currentData.metrics ?? EDGE_METRIC_DEFAULTS,
          selected: currentData.selected ?? false,
        },
      } as Edge;
    });

    return { nodes, edges };
  }

  public async syncGraphState(
    service: GraphService<any>,
    architecture: Architecture,
    refreshFromBackend: boolean = true
  ): Promise<void> {
    await service.waitForGraphReady();
    const graphId = service.getGraphId() ?? service.loadGraphIdFromStorage();
    if (graphId === null) return;
    const payload = this.buildVflowGraph(service, architecture);
    const updated = await this.api.replaceGraphState(graphId, payload);
    if (refreshFromBackend) {
      this.applyGraph(service, architecture, updated);
    } else {
      this.reconcileGraph(service, architecture, updated);
    }
    service.setGraphId(graphId);
  }

  private buildVflowGraph(service: GraphService<any>, architecture: Architecture): VflowGraph {
    const nodes = service.nodes().map((node) => {
      const data = (node as any).data ?? {};
      const type = data.type ?? (node.type as any)?.name ?? 'Unknown';
      const point = (node as any).point ?? {};
      const normalizedPoint = {
        x: typeof point.x === 'number' ? point.x : 0,
        y: typeof point.y === 'number' ? point.y : 0,
      };
      return {
        id: node.id,
        point: normalizedPoint,
        type,
        data: {
          type,
          config: data.config ?? {},
          environment: data.environment ?? architecture,
          fromJson: true,
          selected: Boolean(data.selected),
        },
      };
    });

    const edges = service.edges().map((edge) => {
      const payload = (edge as any).data ?? {};
      const metrics = this.normalizeEdgeMetrics(payload.metrics);
      const reconnectable = edge.reconnectable === 'source' || edge.reconnectable === 'target'
        ? true
        : edge.reconnectable ?? true;
      return {
        id: edge.id,
        source: edge.source,
        target: edge.target,
        config: metrics,
        sourceHandle: edge.sourceHandle ?? null,
        targetHandle: edge.targetHandle ?? null,
        reconnectable,
        floating: edge.floating ?? false,
      };
    });

    return { nodes, edges };
  }

  private normalizeEdgeMetrics(metrics?: EdgeMetrics | null): EdgeMetrics {
    const source = metrics ?? EDGE_METRIC_DEFAULTS;
    return {
      pingMs: this.clampMetric(source.pingMs, EDGE_METRIC_DEFAULTS.pingMs, 0, undefined, true),
      jitterMs: this.clampMetric(source.jitterMs, EDGE_METRIC_DEFAULTS.jitterMs, 0, undefined, true),
      packetloss: this.clampMetric(source.packetloss, EDGE_METRIC_DEFAULTS.packetloss, 0, 1),
      packetlossStddev: this.clampMetric(source.packetlossStddev, EDGE_METRIC_DEFAULTS.packetlossStddev, 0, 1),
    };
  }

  private clampMetric(
    value: number,
    fallback: number,
    min = 0,
    max?: number,
    integer = false
  ): number {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return fallback;
    }
    const adjusted = integer ? Math.round(numeric) : numeric;
    const boundedMin = Math.max(min, adjusted);
    if (max === undefined) {
      return boundedMin;
    }
    return Math.min(max, boundedMin);
  }
}
