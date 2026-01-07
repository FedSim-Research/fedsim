import { Injectable, inject } from '@angular/core';
import { Node, Edge } from 'ngx-vflow';
import { GraphApiService, GraphDetail } from './graph-api.service';
import { GraphService } from './graph-service';
import { ClientNode } from '../components/nodes/client-node/client-node';
import { ServerNode } from '../components/nodes/server-node/server-node';
import { SuperServerNode } from '../components/nodes/super-server-node/super-server-node';

const NODE_TYPE_MAP = {
  ClientNode: ClientNode,
  ServerNode: ServerNode,
  SuperServerNode: SuperServerNode,
} as const;

type Architecture = 'spyker' | 'hierfl';

@Injectable({ providedIn: 'root' })
export class GraphPersistenceService {
  private api = inject(GraphApiService);

  public async initializeGraph(service: GraphService<any>, architecture: Architecture): Promise<void> {
    const storedId = service.loadGraphIdFromStorage();
    if (storedId !== null) {
      const loaded = await this.tryLoadGraph(service, architecture, storedId);
      if (loaded) {
        return;
      }
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
    const nodes: Node[] = [];
    const externalByBackendId = new Map<number, string>();

    for (const node of graph.nodes) {
      const nodeType = NODE_TYPE_MAP[node.type as keyof typeof NODE_TYPE_MAP];
      if (!nodeType) {
        continue;
      }
      externalByBackendId.set(node.node_id, node.external_id);
      nodes.push({
        id: node.external_id,
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
        },
      });
    }

    service.setGraphState(nodes, edges, true);
  }
}
