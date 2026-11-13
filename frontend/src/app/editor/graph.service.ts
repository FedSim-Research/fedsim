import { Injectable, WritableSignal, signal, inject } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge, NodePositionChange } from 'ngx-vflow';
import { GraphHistoryService, State } from './graph-history.service';
import { GraphApiService } from '../api/graph-api.service';
import { EdgeMetrics, EDGE_METRIC_DEFAULTS, normalizeEdgeMetrics } from '../api/edge-metrics';

type NodeWithData = Node & { data?: Record<string, any> };
type EdgeDataPayload = {
  backendId?: number;
  metrics: EdgeMetrics;
  selected?: boolean;
};
type EdgeWithData = Edge & { data?: EdgeDataPayload };

@Injectable({
  providedIn: 'root',
})
export abstract class GraphService<T extends GraphHistoryService> {
  public nodes: WritableSignal<Node[]> = signal([]);
  public edges: WritableSignal<Edge[]> = signal([]);
  protected api = inject(GraphApiService);
  private graphId: number | null = null;
  private pendingEdgeConfig = new Map<string, EdgeMetrics>();
  private pendingGraphReset: Promise<void> = Promise.resolve();

  protected constructor(protected graphHistory: T, private architecture: 'spyker' | 'hierfl'){}

  public getGraphId(): number | null {
    return this.graphId;
  }

  public setGraphId(graphId: number | null): void {
    this.graphId = graphId;
    if (graphId === null) {
      localStorage.removeItem(this.storageKey());
    } else {
      localStorage.setItem(this.storageKey(), String(graphId));
    }
  }

  public loadGraphIdFromStorage(): number | null {
    const raw = localStorage.getItem(this.storageKey());
    if (!raw) return null;
    const parsed = Number(raw);
    return Number.isFinite(parsed) ? parsed : null;
  }

  public setGraphState(nodes: Node[], edges: Edge[], resetHistory: boolean): void {
    const snapshot = this.applyState(nodes, edges);
    if (resetHistory) {
      this.graphHistory.resetHistory(snapshot);
    } else {
      this.graphHistory.saveState(snapshot);
    }
  }

  public applyHistoryState(state: State): void {
    this.applyState(state.nodes, state.edges);
  }

  public addNode(newNode: Node): void {
    this.addEntities([newNode], []);
  }

  public addEdge(newEdge: Edge): void {
    this.addEntities([], [newEdge]);
  }

  /** Adds nodes and edges as one undoable step. */
  protected addEntities(newNodes: Node[], newEdges: Edge[]): void {
    const normalizedEdges = newEdges.map((edge) => this.normalizeEdge(edge));
    this.nodes.update((nodes) => [...nodes, ...newNodes]);
    this.edges.update((edges) => [...edges, ...normalizedEdges]);
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    for (const node of newNodes) {
      void this.persistCreateNode(node);
    }
    for (const edge of normalizedEdges) {
      void this.persistCreateEdge(edge);
    }
  }

  public removeNodeById(nodeId: string): void {
    this.removeEntities([nodeId], []);
  }

  public removeEdge(edge: Edge): void {
    this.removeEntities([], [edge.id]);
  }

  public removeEdgeById(edgeId: string): void {
    this.removeEntities([], [edgeId]);
  }

  /** Removes nodes (with their attached edges) and edges as one undoable step. */
  public removeEntities(nodeIds: Iterable<string>, edgeIds: Iterable<string>): void {
    const doomedNodes = new Set(nodeIds);
    const doomedEdges = new Set(edgeIds);
    const removedNodes = this.nodes().filter((node) => doomedNodes.has(node.id));
    const isRemovedEdge = (edge: Edge) =>
      doomedEdges.has(edge.id) || doomedNodes.has(edge.source) || doomedNodes.has(edge.target);
    const removedEdges = this.edges().filter(isRemovedEdge);
    if (!removedNodes.length && !removedEdges.length) {
      return;
    }

    for (const node of removedNodes) {
      const backendId = (node as NodeWithData).data?.['backendId'] as string | undefined;
      if (backendId !== undefined) {
        void this.api.deleteNode(backendId).catch(() => undefined);
      }
    }
    for (const edge of removedEdges) {
      // Edges attached to a deleted node are removed together with it in the backend.
      if (doomedNodes.has(edge.source) || doomedNodes.has(edge.target)) continue;
      const backendId = (edge as EdgeWithData).data?.backendId ?? this.extractNumericId(edge.id);
      if (backendId !== null && backendId !== undefined) {
        void this.api.deleteEdge(backendId).catch(() => undefined);
      }
    }
    for (const edge of removedEdges) {
      this.pendingEdgeConfig.delete(edge.id);
    }

    this.nodes.update((nodes) => nodes.filter((node) => !doomedNodes.has(node.id)));
    this.edges.update((edges) => edges.filter((edge) => !isRemovedEdge(edge)));
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
  }

  public updateEdgeMetrics(edgeId: string, metrics: EdgeMetrics): void {
    const normalized = normalizeEdgeMetrics(metrics);
    let backendId: number | undefined;
    this.edges.update((edges) =>
      edges.map((edge) => {
        if (edge.id !== edgeId) return edge;
        const payload = (edge as EdgeWithData).data ?? { metrics: normalized };
        backendId = payload.backendId;
        return {
          ...edge,
          data: { ...payload, metrics: normalized },
        } as EdgeWithData;
      })
    );
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    const targetId = backendId ?? this.extractNumericId(edgeId);
    if (targetId === undefined || targetId === null) {
      this.pendingEdgeConfig.set(edgeId, normalized);
      return;
    }
    this.pendingEdgeConfig.delete(edgeId);
    void this.api.updateEdge(targetId, { config: normalized }).catch(() => undefined);
  }

  public async resetGraph(): Promise<void> {
    const hadContent = this.nodes().length > 0 || this.edges().length > 0;
    const emptyState = this.applyState([], []);
    if (hadContent) {
      this.graphHistory.saveState(emptyState);
    } else {
      this.graphHistory.resetHistory(emptyState);
    }
    this.pendingGraphReset = this.pendingGraphReset
      .catch(() => undefined)
      .then(() => this.resetGraphInBackend());
    await this.pendingGraphReset;
  }

  public getGraphHistory(){
    return this.graphHistory
  }

  public async waitForGraphReady(): Promise<void> {
    await this.pendingGraphReset.catch(() => undefined);
  }

  public updateNodePositions(posChanges: NodePositionChange[]){
    const changeMap = new Map(posChanges.map(c => [c.id, c.point]));
    const newNodes = this.nodes().map(node => {
    if (changeMap.has(node.id)) {
      return {
        ...node,
        point: changeMap.get(node.id)!
      };
    }
    return node;
  });
  this.nodes.set(newNodes);
  void this.persistPositionUpdates(posChanges);
  }

  public updateNodeConfig(nodeId: string, configPatch: Record<string, unknown>): void {
    let backendId: string | undefined;
    this.nodes.update((nodes) =>
      nodes.map((node) => {
        if (node.id !== nodeId) return node;
        const nodeData = (node as NodeWithData).data ?? {};
        const currentConfig = (nodeData['config'] as Record<string, unknown>) ?? {};
        backendId = nodeData['backendId'] as string | undefined;
        return {
          ...node,
          data: {
            ...nodeData,
            config: { ...currentConfig, ...configPatch },
          },
        } as NodeWithData;
      })
    );
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });

    if (backendId === undefined) return;
    const updatedNode = this.nodes().find((n) => n.id === nodeId) as NodeWithData | undefined;
    const updatedConfig =
      ((updatedNode?.data?.['config'] as Record<string, unknown>) ?? configPatch);
    void this.api.updateNode(backendId, { config: updatedConfig }).catch(() => undefined);
  }

  private applyState(nodes: Node[], edges: Edge[]): State {
    const normalizedEdges = edges.map((edge) => this.normalizeEdge(edge));
    const snapshot = { nodes, edges: normalizedEdges };
    this.nodes.set(nodes);
    this.edges.set(normalizedEdges);
    return snapshot;
  }

  private normalizeEdge(edge: Edge): EdgeWithData {
    return this.withEdgeLabel(this.withEdgeMetrics(edge));
  }

  private withEdgeMetrics(edge: Edge): EdgeWithData {
    const payload = (edge as EdgeWithData).data ?? { metrics: EDGE_METRIC_DEFAULTS };
    const normalizedMetrics = normalizeEdgeMetrics(payload.metrics);
    return {
      ...edge,
      data: { ...payload, metrics: normalizedMetrics },
    };
  }

  private withEdgeLabel(edge: EdgeWithData): EdgeWithData {
    const labels = edge.edgeLabels ?? {};
    if (labels.center?.type === 'html-template') {
      return edge;
    }
    return {
      ...edge,
      edgeLabels: {
        ...labels,
        center: {
          type: 'html-template',
          data: { edgeId: edge.id },
        },
      },
    };
  }

  protected async persistCreateNode(newNode: Node): Promise<void> {
    await this.waitForGraphReady();
    if (this.graphId === null) return;
    const data = (newNode as NodeWithData).data ?? {};
    const point = (newNode as any)?.point ?? {};
    const position = {
      x: typeof point.x === 'number' ? point.x : 0,
      y: typeof point.y === 'number' ? point.y : 0,
    };
    const payload = {
      type: data['type'],
      config: data['config'] ?? {},
      position,
    };
    void this.api.createNode(this.graphId, payload).then((created) => {
      const oldId = newNode.id;
      this.nodes.update((nodes) =>
        nodes.map((node) => {
          if (node.id !== oldId) return node;
          const nodeData = (node as NodeWithData).data ?? {};
          return {
            ...node,
            id: created.node_id,
            data: { ...nodeData, backendId: created.node_id, config: created.config },
          };
        })
      );
      this.edges.update((edges) =>
        edges.map((edge) => {
          if (edge.source === oldId || edge.target === oldId) {
            return {
              ...edge,
              source: edge.source === oldId ? created.node_id : edge.source,
              target: edge.target === oldId ? created.node_id : edge.target,
            };
          }
          return edge;
        })
      );
      this.persistPendingEdgesForNode(created.node_id);
    }).catch(() => undefined);
  }

  protected async persistCreateEdge(newEdge: Edge): Promise<void> {
    await this.waitForGraphReady();
    if (this.graphId === null) return;
    const edgeInState = this.edges().find((edge) => edge.id === newEdge.id) as EdgeWithData | undefined;
    const existingBackendId = edgeInState?.data?.backendId;
    if (existingBackendId !== undefined) return;
    const sourceNode = this.nodes().find((n) => n.id === newEdge.source) as NodeWithData | undefined;
    const targetNode = this.nodes().find((n) => n.id === newEdge.target) as NodeWithData | undefined;
    const sourceBackend = sourceNode?.data?.['backendId'] as string | undefined;
    const targetBackend = targetNode?.data?.['backendId'] as string | undefined;
    if (!sourceBackend || !targetBackend) {
      return;
    }
    const metrics = edgeInState?.data?.metrics ?? EDGE_METRIC_DEFAULTS;
    const payload = {
      source_node_id: sourceBackend,
      target_node_id: targetBackend,
      config: metrics,
    };
    void this.api.createEdge(this.graphId, payload).then((created) => {
      this.edges.update((edges) =>
        edges.map((edge) => {
          if (edge.id !== newEdge.id) return edge;
          const edgeData = (edge as EdgeWithData).data ?? {};
          return { ...edge, data: { ...edgeData, backendId: created.edge_id } } as Edge;
        })
      );
      const pending = this.pendingEdgeConfig.get(newEdge.id);
      if (pending) {
        this.pendingEdgeConfig.delete(newEdge.id);
        void this.api.updateEdge(created.edge_id, { config: pending }).catch(() => undefined);
      }
    }).catch(() => undefined);
  }

  private persistPendingEdgesForNode(nodeId: string): void {
    const candidateEdges = this.edges().filter((edge) =>
      edge.source === nodeId || edge.target === nodeId
    );
    for (const edge of candidateEdges) {
      const backendId = (edge as EdgeWithData).data?.backendId;
      if (backendId !== undefined) continue;
      this.persistCreateEdge(edge);
    }
  }

  private async persistPositionUpdates(posChanges: NodePositionChange[]): Promise<void> {
    await this.waitForGraphReady();
    if (this.graphId === null) return;
    for (const change of posChanges) {
      const node = this.nodes().find((n) => n.id === change.id) as NodeWithData | undefined;
    const backendId = node?.data?.['backendId'] as string | undefined;
    if (backendId === undefined) continue;
    void this.api.updateNode(backendId, { position: change.point }).catch(() => undefined);
    }
  }

  private async resetGraphInBackend(): Promise<void> {
    const graphIdToDelete = this.graphId;
    this.setGraphId(null);
    if (graphIdToDelete !== null) {
      await this.api.deleteGraph(graphIdToDelete).catch(() => undefined);
    }
    const created = await this.api.createGraph({
      name: `${this.architecture}-graph`,
      architecture: this.architecture,
      metadata: null,
    }).catch(() => null);
    if (created) {
      this.setGraphId(created.graph_id);
    }
  }

  private storageKey(): string {
    return `fedsim.graphId.${this.architecture}`;
  }

  private extractNumericId(edgeId: string): number | null {
    return typeof edgeId === 'string' && /^\d+$/.test(edgeId) ? Number(edgeId) : null;
  }
}
