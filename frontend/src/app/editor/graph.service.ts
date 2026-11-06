import { Injectable, WritableSignal, signal, inject } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge, NodePositionChange } from 'ngx-vflow';
import { GraphHistoryService, State } from './graph-history.service';
import { GraphApiService } from '../api/graph-api.service';
import { EdgeMetrics, EDGE_METRIC_DEFAULTS } from '../api/edge-metrics';

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
    this.nodes.update((nodes) => [...nodes, newNode]);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
    void this.persistCreateNode(newNode);
  }

  public addEdge(newEdge: Edge) {
    const normalizedEdge = this.normalizeEdge(newEdge);
    this.edges.update((edges) => [...edges, normalizedEdge]);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
    void this.persistCreateEdge(normalizedEdge);
  }

  public removeNodeById(nodeId: String){
    const node = this.nodes().find((n) => n.id === nodeId) as NodeWithData | undefined;
    const backendId = node?.data?.['backendId'] as string | undefined;
    if (backendId !== undefined) {
      void this.api.deleteNode(backendId).catch(() => undefined);
    }
    this.nodes.update(nodes => nodes.filter(node => node.id !== nodeId));
    this.edges.update(edges => edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public removeEdge(edgeToRemove: Edge){
    const edge = edgeToRemove as EdgeWithData;
    const backendId = edge.data?.backendId;
    if (backendId !== undefined) {
      void this.api.deleteEdge(backendId).catch(() => undefined);
    }
    this.pendingEdgeConfig.delete(edge.id);
    this.edges.update(edges => edges.filter(edge => edge !== edgeToRemove));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public removeEdgeById(edgeId: String){
    const edge = this.edges().find((e) => e.id === edgeId) as EdgeWithData | undefined;
    const backendId = edge?.data?.backendId;
    if (backendId !== undefined) {
      void this.api.deleteEdge(backendId).catch(() => undefined);
    } else if (typeof edgeId === 'string' && /^\d+$/.test(edgeId)) {
      void this.api.deleteEdge(Number(edgeId)).catch(() => undefined);
    }
    this.pendingEdgeConfig.delete(String(edgeId));
    this.edges.update(edges => edges.filter(edge => edge.id !== edgeId));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public updateEdgeMetrics(edgeId: string, metrics: EdgeMetrics): void {
    const normalized = this.normalizeEdgeMetrics(metrics);
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

  protected onStateApplied(_state: State): void {}

  private applyState(nodes: Node[], edges: Edge[]): State {
    const normalizedEdges = edges.map((edge) => this.normalizeEdge(edge));
    const snapshot = { nodes, edges: normalizedEdges };
    this.nodes.set(nodes);
    this.edges.set(normalizedEdges);
    this.onStateApplied(snapshot);
    return snapshot;
  }

  private normalizeEdge(edge: Edge): EdgeWithData {
    return this.withEdgeLabel(this.withEdgeMetrics(edge));
  }

  private withEdgeMetrics(edge: Edge): EdgeWithData {
    const payload = (edge as EdgeWithData).data ?? { metrics: EDGE_METRIC_DEFAULTS };
    const normalizedMetrics = this.normalizeEdgeMetrics(payload.metrics);
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

  private normalizeEdgeMetrics(metrics?: EdgeMetrics | null): EdgeMetrics {
    const source = metrics ?? EDGE_METRIC_DEFAULTS;
    return {
      pingMs: this.clampMetric(source.pingMs, EDGE_METRIC_DEFAULTS.pingMs),
      jitterMs: this.clampMetric(source.jitterMs, EDGE_METRIC_DEFAULTS.jitterMs),
      packetloss: this.clampMetric(source.packetloss, EDGE_METRIC_DEFAULTS.packetloss, 0, 1),
      packetlossStddev: this.clampMetric(source.packetlossStddev, EDGE_METRIC_DEFAULTS.packetlossStddev, 0, 1),
    };
  }

  private clampMetric(value: number, fallback: number, min = 0, max?: number): number {
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return fallback;
    }
    const boundedMin = Math.max(min, numeric);
    if (max === undefined) {
      return boundedMin;
    }
    return Math.min(max, boundedMin);
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
