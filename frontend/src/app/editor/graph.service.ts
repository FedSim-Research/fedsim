import { Injectable, WritableSignal, signal, inject } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge, NodePositionChange } from 'ngx-vflow';
import { GraphHistoryService, State } from './graph-history.service';
import { GraphApiService } from '../api/graph-api.service';
import { EdgeMetrics, EDGE_METRIC_DEFAULTS, normalizeEdgeMetrics } from '../api/edge-metrics';
import { toVflowGraph } from './graph-serialization';

/** Edits within this window are written to the backend as one request. */
const SAVE_DEBOUNCE_MS = 300;

type NodeWithData = Node & { data?: Record<string, any> };
type EdgeDataPayload = {
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
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private saveQueue: Promise<void> = Promise.resolve();
  private hasUnsavedChanges = false;

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

  /** Steps back in history. Returns false when there was nothing to undo. */
  public undo(): boolean {
    return this.moveInHistory(() => this.graphHistory.undo());
  }

  /** Re-applies an undone step. Returns false when there was nothing to redo. */
  public redo(): boolean {
    return this.moveInHistory(() => this.graphHistory.redo());
  }

  private moveInHistory(step: () => void): boolean {
    const before = this.graphHistory.getState();
    step();
    const after = this.graphHistory.getState();
    if (after === before) {
      return false;
    }
    this.applyState(after.nodes, after.edges);
    this.scheduleSave();
    return true;
  }

  public addNode(newNode: Node): void {
    this.addEntities([newNode], []);
  }

  public addEdge(newEdge: Edge): void {
    this.addEntities([], [newEdge]);
  }

  /** Adds nodes and edges as one undoable step. */
  public addEntities(newNodes: Node[], newEdges: Edge[]): void {
    const normalizedEdges = newEdges.map((edge) => this.normalizeEdge(edge));
    this.nodes.update((nodes) => [...nodes, ...newNodes]);
    this.edges.update((edges) => [...edges, ...normalizedEdges]);
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    this.scheduleSave();
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
    const isRemovedEdge = (edge: Edge) =>
      doomedEdges.has(edge.id) || doomedNodes.has(edge.source) || doomedNodes.has(edge.target);
    const removesNodes = this.nodes().some((node) => doomedNodes.has(node.id));
    if (!removesNodes && !this.edges().some(isRemovedEdge)) {
      return;
    }

    this.nodes.update((nodes) => nodes.filter((node) => !doomedNodes.has(node.id)));
    this.edges.update((edges) => edges.filter((edge) => !isRemovedEdge(edge)));
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    this.scheduleSave();
  }

  public updateEdgeMetrics(edgeId: string, metrics: EdgeMetrics): void {
    const normalized = normalizeEdgeMetrics(metrics);
    this.edges.update((edges) =>
      edges.map((edge) => {
        if (edge.id !== edgeId) return edge;
        const payload = (edge as EdgeWithData).data ?? { metrics: normalized };
        return {
          ...edge,
          data: { ...payload, metrics: normalized },
        } as EdgeWithData;
      })
    );
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    this.scheduleSave();
  }

  /** Replaces the whole graph content as one undoable step, e.g. for imports. */
  public replaceContents(nodes: Node[], edges: Edge[]): void {
    this.applyState(nodes, edges);
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    this.scheduleSave();
  }

  /** Removes all nodes and edges; the graph itself and its settings are kept. */
  public resetGraph(): void {
    if (this.nodes().length || this.edges().length) {
      this.replaceContents([], []);
    }
  }

  public getGraphHistory(){
    return this.graphHistory
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
  this.scheduleSave();
  }

  public updateNodeConfig(nodeId: string, configPatch: Record<string, unknown>): void {
    this.nodes.update((nodes) =>
      nodes.map((node) => {
        if (node.id !== nodeId) return node;
        const nodeData = (node as NodeWithData).data ?? {};
        const currentConfig = (nodeData['config'] as Record<string, unknown>) ?? {};
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
    this.scheduleSave();
  }

  /** Forgets the open graph after it was deleted elsewhere; pending edits are dropped. */
  public detachGraph(): void {
    if (this.saveTimer !== null) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    this.hasUnsavedChanges = false;
    this.setGraphId(null);
    this.setGraphState([], [], true);
  }

  /** Writes pending changes now. Saves run strictly one after another. */
  public flushSave(): Promise<void> {
    if (this.saveTimer !== null) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    this.saveQueue = this.saveQueue.then(() => this.saveNow());
    return this.saveQueue;
  }

  /** Persists the current state shortly; bursts of edits are coalesced into one request. */
  protected scheduleSave(): void {
    this.hasUnsavedChanges = true;
    if (this.saveTimer !== null) {
      clearTimeout(this.saveTimer);
    }
    this.saveTimer = setTimeout(() => void this.flushSave(), SAVE_DEBOUNCE_MS);
  }

  private async saveNow(): Promise<void> {
    if (!this.hasUnsavedChanges || this.graphId === null) {
      return;
    }
    this.hasUnsavedChanges = false;
    try {
      const payload = toVflowGraph(this.architecture, this.nodes(), this.edges());
      await this.api.replaceGraphState(this.graphId, payload);
    } catch {
      // The interceptor already reported it; the next edit retries with the full state.
      this.hasUnsavedChanges = true;
    }
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

  private storageKey(): string {
    return `fedsim.graphId.${this.architecture}`;
  }
}
