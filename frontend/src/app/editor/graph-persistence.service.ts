import { Injectable, inject } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge } from 'ngx-vflow';
import { GraphApiService, GraphDetail } from '../api/graph-api.service';
import { GraphService } from './graph.service';
import { EDGE_METRIC_DEFAULTS } from '../api/edge-metrics';
import { State } from './graph-history.service';
import { Architecture, isNodeKind } from '../domain/topology';
import { createGraphNode } from './nodes/node-factory';

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

    for (const node of graph.nodes) {
      if (!isNodeKind(node.type)) {
        continue;
      }
      nodes.push(createGraphNode({
        id: node.node_id,
        kind: node.type,
        architecture,
        point: node.position,
        config: node.config,
      }));
    }

    const nodeIds = new Set(nodes.map((node) => node.id));
    const edges: Edge[] = graph.edges
      .filter((edge) => nodeIds.has(edge.source_node_id) && nodeIds.has(edge.target_node_id))
      .map((edge) => ({
        id: String(edge.edge_id),
        source: edge.source_node_id,
        target: edge.target_node_id,
        reconnectable: true,
        floating: false,
        data: { metrics: edge.config ?? EDGE_METRIC_DEFAULTS },
      }));

    return { nodes, edges };
  }
}
