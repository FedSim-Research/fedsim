import { Injectable, inject } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge } from 'ngx-vflow';
import { GraphApiService, GraphDetail } from '../api/graph-api.service';
import { GraphService } from './graph.service';
import { ClientNode } from './nodes/client-node/client-node';
import { ServerNode } from './nodes/server-node/server-node';
import { SuperServerNode } from './nodes/super-server-node/super-server-node';
import { EDGE_METRIC_DEFAULTS } from '../api/edge-metrics';
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

  /** Loads a stored graph into the given workspace and makes it the active graph. */
  public async loadGraph(
    service: GraphService<any>,
    architecture: Architecture,
    graphId: number
  ): Promise<void> {
    // Edits still waiting for their debounced save belong to the graph that is open now.
    await service.flushSave();
    const graph = await this.api.getGraph(graphId);
    this.applyGraph(service, architecture, graph);
    service.setGraphId(graphId);
  }

  private async tryLoadGraph(
    service: GraphService<any>,
    architecture: Architecture,
    graphId: number
  ): Promise<boolean> {
    try {
      await this.loadGraph(service, architecture, graphId);
      return true;
    } catch {
      return false;
    }
  }

  private applyGraph(service: GraphService<any>, architecture: Architecture, graph: GraphDetail): void {
    const snapshot = this.toStateSnapshot(architecture, graph);
    service.setGraphState(snapshot.nodes, snapshot.edges, true);
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
          metrics: edge.config ?? EDGE_METRIC_DEFAULTS,
        },
      });
    }

    return { nodes, edges };
  }
}
