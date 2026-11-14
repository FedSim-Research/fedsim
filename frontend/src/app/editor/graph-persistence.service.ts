import { Injectable, inject } from '@angular/core';
import { HttpErrorResponse } from '@angular/common/http';
import { StaticNode as Node, StaticEdge as Edge } from 'ngx-vflow';
import { GraphApiService, GraphDetail } from '../api/graph-api.service';
import { GraphService } from './graph.service';
import { EDGE_METRIC_DEFAULTS } from '../api/edge-metrics';
import { GraphState } from './graph-history';
import { Architecture, isNodeKind } from '../domain/topology';
import { createGraphNode } from './nodes/node-factory';

@Injectable({ providedIn: 'root' })
export class GraphPersistenceService {
  private api = inject(GraphApiService);
  private readonly loadGenerations = new WeakMap<GraphService, number>();

  public async initializeGraph(
    service: GraphService,
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
      service.loadContents([], []);
      return;
    }

    const created = await this.api.createGraph({
      name: `${architecture}-graph`,
      architecture,
      metadata: null,
    });
    service.setGraphId(created.graph_id);
    service.loadContents([], []);
  }

  /** Loads a stored graph into the given workspace and makes it the active graph. */
  public async loadGraph(
    service: GraphService,
    architecture: Architecture,
    graphId: number
  ): Promise<void> {
    // Edits still waiting for their debounced save belong to the graph that is open now.
    const generation = (this.loadGenerations.get(service) ?? 0) + 1;
    const previousGraphId = service.getGraphId();
    this.loadGenerations.set(service, generation);
    await service.flushSave();
    const editRevision = service.getEditRevision();
    const graph = await this.api.getGraph(graphId);
    if (this.loadGenerations.get(service) !== generation || service.getGraphId() !== previousGraphId) return;
    if (graph.architecture !== architecture) {
      throw new Error(`Cannot load a ${graph.architecture} graph into ${architecture}.`);
    }
    // Edits may also have arrived while the requested graph was being fetched.
    await service.flushSave();
    if (this.loadGenerations.get(service) !== generation || service.getGraphId() !== previousGraphId) return;
    // A reload response predates edits just flushed to the same graph. Keep
    // those local contents instead of replacing them with the stale response.
    if (graphId === previousGraphId && service.getEditRevision() !== editRevision) return;
    this.applyGraph(service, architecture, graph);
    service.setGraphId(graphId);
  }

  private async tryLoadGraph(
    service: GraphService,
    architecture: Architecture,
    graphId: number
  ): Promise<boolean> {
    try {
      await this.loadGraph(service, architecture, graphId);
      return true;
    } catch (error) {
      if (error instanceof HttpErrorResponse && error.status === 404) return false;
      throw error;
    }
  }

  private applyGraph(service: GraphService, architecture: Architecture, graph: GraphDetail): void {
    const snapshot = this.toStateSnapshot(architecture, graph);
    service.loadContents(snapshot.nodes, snapshot.edges);
  }

  private toStateSnapshot(architecture: Architecture, graph: GraphDetail): GraphState {
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
