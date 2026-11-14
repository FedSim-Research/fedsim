import { WritableSignal, signal, inject } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge, NodePositionChange } from 'ngx-vflow';
import { GraphHistory, GraphState } from './graph-history';
import { GraphApiService } from '../api/graph-api.service';
import { EdgeMetrics, EDGE_METRIC_DEFAULTS, normalizeEdgeMetrics } from '../api/edge-metrics';
import { toVflowGraph } from './graph-serialization';
import { Architecture, NodeKind } from '../domain/topology';
import { nodeLimitViolation } from '../domain/node-limits';

/** Edits within this window are written to the backend as one request. */
const SAVE_DEBOUNCE_MS = 300;

type NodeWithData = Node & { data?: { type?: NodeKind; config?: Record<string, unknown> } };
type EdgeDataPayload = {
  metrics: EdgeMetrics;
  selected?: boolean;
};
type EdgeWithData = Edge & { data?: EdgeDataPayload };

/**
 * Editor state of one architecture's graph: nodes, edges, undo history and the
 * debounced saving to the backend. Subclasses add topology specific behaviour.
 */
export abstract class GraphService {
  public nodes: WritableSignal<Node[]> = signal([]);
  public edges: WritableSignal<Edge[]> = signal([]);
  protected api = inject(GraphApiService);
  private graphId: number | null = null;
  private graphGeneration = 0;
  private saveTimer: ReturnType<typeof setTimeout> | null = null;
  private saveQueue: Promise<void> = Promise.resolve();
  private hasUnsavedChanges = false;
  private editRevision = 0;
  protected readonly graphHistory = new GraphHistory();

  protected constructor(public readonly architecture: Architecture) {}

  public getGraphId(): number | null {
    return this.graphId;
  }

  public getEditRevision(): number {
    return this.editRevision;
  }

  public setGraphId(graphId: number | null): void {
    if (graphId !== this.graphId) this.graphGeneration += 1;
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
    return Number.isSafeInteger(parsed) && parsed > 0 ? parsed : null;
  }

  /** Shows a stored graph: replaces the content and starts a fresh history. Nothing is saved. */
  public loadContents(nodes: Node[], edges: Edge[]): void {
    this.graphHistory.resetHistory(this.applyState(nodes, edges));
  }

  /** Adds a node. Returns why it was rejected, or null when it was added. */
  public addNode(newNode: Node): string | null {
    return this.addEntities([newNode], []);
  }

  public addEdge(newEdge: Edge): void {
    this.addEntities([], [newEdge]);
  }

  /**
   * Adds nodes and edges as one undoable step.
   * Returns why nothing was added (e.g. a node limit), or null on success.
   */
  public addEntities(newNodes: Node[], newEdges: Edge[]): string | null {
    const violation = nodeLimitViolation(this.architecture, kindsOf(this.nodes()), kindsOf(newNodes));
    if (violation) {
      return violation;
    }
    const normalizedEdges = [...newEdges, ...this.linksForNewNodes(newNodes)].map((edge) => this.normalizeEdge(edge));
    this.nodes.update((nodes) => [...nodes, ...newNodes]);
    this.edges.update((edges) => [...edges, ...normalizedEdges]);
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    this.scheduleSave();
    return null;
  }

  public removeNodeById(nodeId: string): void {
    this.removeEntities([nodeId], []);
  }

  public removeEdge(edge: Edge): void {
    this.removeEntities([], [edge.id]);
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

  public updateNodeConfig(nodeId: string, configPatch: Record<string, unknown>): void {
    this.nodes.update((nodes) =>
      nodes.map((node) => {
        if (node.id !== nodeId) return node;
        const nodeData = (node as NodeWithData).data ?? {};
        const currentConfig = nodeData.config ?? {};
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

  /** Shows intermediate drag positions; neither recorded in history nor saved. */
  public previewPositions(changes: NodePositionChange[]): void {
    const points = new Map(changes.map((change) => [change.id, change.point]));
    this.nodes.update((nodes) =>
      nodes.map((node) => {
        const point = points.get(node.id);
        return point ? { ...node, point } : node;
      }),
    );
  }

  /** Commits a finished drag as one undoable step. */
  public moveNodes(changes: NodePositionChange[]): void {
    const points = new Map(changes.map((change) => [change.id, change.point]));
    const nodes = this.nodes().map((node) => {
      const point = points.get(node.id);
      return point ? { ...node, point } : node;
    });
    this.nodes.set(nodes);
    this.edges.set(this.linksAfterMove(nodes, this.edges()));
    this.graphHistory.saveState({ nodes: this.nodes(), edges: this.edges() });
    this.scheduleSave();
  }

  /**
   * Marks exactly the given nodes and edges as selected. Selection is view state:
   * it is neither recorded in history nor saved.
   */
  public setSelection(nodeIds: ReadonlySet<string>, edgeIds: ReadonlySet<string>): void {
    this.nodes.set(withSelection(this.nodes(), nodeIds));
    this.edges.set(withSelection(this.edges(), edgeIds));
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

  /** Steps back in history. Returns false when there was nothing to undo. */
  public undo(): boolean {
    return this.moveInHistory(() => this.graphHistory.undo());
  }

  /** Re-applies an undone step. Returns false when there was nothing to redo. */
  public redo(): boolean {
    return this.moveInHistory(() => this.graphHistory.redo());
  }

  /** Forgets the open graph after it was deleted elsewhere; pending edits are dropped. */
  public detachGraph(): void {
    if (this.saveTimer !== null) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    this.hasUnsavedChanges = false;
    this.setGraphId(null);
    this.loadContents([], []);
  }

  /** Writes pending changes now. Saves run strictly one after another. */
  public flushSave(): Promise<void> {
    if (this.saveTimer !== null) {
      clearTimeout(this.saveTimer);
      this.saveTimer = null;
    }
    const operation = this.saveQueue.then(() => this.saveNow());
    // Explicit callers must see failures, without poisoning subsequent retries.
    this.saveQueue = operation.catch(() => undefined);
    return operation;
  }

  /** Topology hook: edges an architecture adds automatically for new nodes. */
  protected linksForNewNodes(_newNodes: Node[]): Edge[] {
    return [];
  }

  /** Topology hook: adjusts edges after nodes moved. Must return `edges` itself when nothing changed. */
  protected linksAfterMove(_nodes: Node[], edges: Edge[]): Edge[] {
    return edges;
  }

  /** Persists the current state shortly; bursts of edits are coalesced into one request. */
  protected scheduleSave(): void {
    this.editRevision += 1;
    this.hasUnsavedChanges = true;
    if (this.saveTimer !== null) {
      clearTimeout(this.saveTimer);
    }
    this.saveTimer = setTimeout(() => void this.flushSave().catch(() => undefined), SAVE_DEBOUNCE_MS);
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

  private async saveNow(): Promise<void> {
    while (this.hasUnsavedChanges && this.graphId !== null) {
      const graphId = this.graphId;
      const generation = this.graphGeneration;
      this.hasUnsavedChanges = false;
      try {
        const payload = toVflowGraph(this.architecture, this.nodes(), this.edges());
        await this.api.replaceGraphState(graphId, payload);
      } catch (error) {
        // Keep edits retryable, unless this graph was detached while saving.
        if (generation === this.graphGeneration) this.hasUnsavedChanges = true;
        throw error;
      }
      if (generation !== this.graphGeneration) return;
    }
  }

  private applyState(nodes: Node[], edges: Edge[]): GraphState {
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

function kindsOf(nodes: Node[]): NodeKind[] {
  return nodes.map((node) => (node as NodeWithData).data?.type as NodeKind);
}

/** Returns `items` with updated selection flags, keeping unchanged items (and the array) as they are. */
function withSelection<T extends { id: string }>(items: T[], selectedIds: ReadonlySet<string>): T[] {
  let changed = false;
  const next = items.map((item) => {
    const data = (item as { data?: { selected?: boolean } }).data ?? {};
    const selected = selectedIds.has(item.id);
    if (Boolean(data.selected) === selected) {
      return item;
    }
    changed = true;
    return { ...item, data: { ...data, selected } };
  });
  return changed ? next : items;
}
