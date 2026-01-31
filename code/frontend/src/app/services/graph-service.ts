import { Injectable, WritableSignal, signal, inject } from '@angular/core';
import { Node, Edge, NodePositionChange } from 'ngx-vflow';
import { GraphHistoryService } from './graph-history.service';
import { GraphApiService } from './graph-api.service';

type NodeWithData = Node & { data?: Record<string, any> };
type EdgeWithData = Edge & { data?: Record<string, any> };

@Injectable({
  providedIn: 'root',
})
export abstract class GraphService<T extends GraphHistoryService> {
  public nodes: WritableSignal<Node[]> = signal([]);
  public edges: WritableSignal<Edge[]> = signal([]);
  protected api = inject(GraphApiService);
  private graphId: number | null = null;

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
    this.nodes.set(nodes);
    this.edges.set(edges);
    if (resetHistory) {
      this.graphHistory.resetHistory({ nodes, edges });
    } else {
      this.graphHistory.saveState({ nodes, edges });
    }
  }

  public addNode(newNode: Node): void {
    const normalized = this.normalizeNodeId(newNode);
    this.nodes.update((nodes) => [...nodes, normalized]);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
    void this.persistCreateNode(normalized);
  }

  public addEdge(newEdge: Edge) {
    this.edges.update((edges) => [...edges, newEdge]);
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
    void this.persistCreateEdge(newEdge);
  }

  public removeNodeById(nodeId: String){
    const node = this.nodes().find((n) => n.id === nodeId) as NodeWithData | undefined;
    const backendId = node?.data?.['backendId'] as number | undefined;
    if (backendId !== undefined) {
      void this.api.deleteNode(backendId).catch(() => undefined);
    }
    this.nodes.update(nodes => nodes.filter(node => node.id !== nodeId));
    this.edges.update(edges => edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public removeEdge(edgeToRemove: Edge){
    const edge = edgeToRemove as EdgeWithData;
    const backendId = edge.data?.['backendId'] as number | undefined;
    if (backendId !== undefined) {
      void this.api.deleteEdge(backendId).catch(() => undefined);
    }
    this.edges.update(edges => edges.filter(edge => edge !== edgeToRemove));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public removeEdgeById(edgeId: String){
    const edge = this.edges().find((e) => e.id === edgeId) as EdgeWithData | undefined;
    const backendId = edge?.data?.['backendId'] as number | undefined;
    if (backendId !== undefined) {
      void this.api.deleteEdge(backendId).catch(() => undefined);
    } else if (typeof edgeId === 'string' && /^\d+$/.test(edgeId)) {
      void this.api.deleteEdge(Number(edgeId)).catch(() => undefined);
    }
    this.edges.update(edges => edges.filter(edge => edge.id !== edgeId));
    this.graphHistory.saveState({nodes: this.nodes(), edges: this.edges()});
  }

  public resetGraph(){
    this.nodes.set([]);
    this.edges.set([]);
    this.graphHistory.resetHistory({nodes: this.nodes(), edges: this.edges()});
    void this.resetGraphInBackend();
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
  void this.persistPositionUpdates(posChanges);
  }

  protected persistCreateNode(newNode: Node): void {
    if (this.graphId === null) return;
    const data = (newNode as NodeWithData).data ?? {};
    const point = (newNode as any)?.point ?? {};
    const position = {
      x: typeof point.x === 'number' ? point.x : 0,
      y: typeof point.y === 'number' ? point.y : 0,
    };
    const payload = {
      external_id: newNode.id,
      type: data.type,
      config: data.config ?? {},
      position,
    };
    void this.api.createNode(this.graphId, payload).then((created) => {
      this.nodes.update((nodes) =>
        nodes.map((node) => {
          if (node.id !== newNode.id) return node;
          const nodeData = (node as NodeWithData).data ?? {};
          return {
            ...node,
            data: { ...nodeData, backendId: created.node_id },
          };
        })
      );
      this.persistPendingEdgesForNode(newNode.id);
    }).catch(() => undefined);
  }

  protected persistCreateEdge(newEdge: Edge): void {
    if (this.graphId === null) return;
    const existingBackendId = (newEdge as EdgeWithData).data?.['backendId'] as number | undefined;
    if (existingBackendId !== undefined) return;
    const sourceNode = this.nodes().find((n) => n.id === newEdge.source) as NodeWithData | undefined;
    const targetNode = this.nodes().find((n) => n.id === newEdge.target) as NodeWithData | undefined;
    const sourceBackend = sourceNode?.data?.['backendId'] as number | undefined;
    const targetBackend = targetNode?.data?.['backendId'] as number | undefined;
    if (sourceBackend === undefined || targetBackend === undefined) {
      return;
    }
    const payload = {
      source_external_id: newEdge.source,
      target_external_id: newEdge.target,
    };
    void this.api.createEdge(this.graphId, payload).then((created) => {
      this.edges.update((edges) =>
        edges.map((edge) => {
          if (edge.id !== newEdge.id) return edge;
          const edgeData = (edge as EdgeWithData).data ?? {};
          return { ...edge, data: { ...edgeData, backendId: created.edge_id } } as Edge;
        })
      );
    }).catch(() => undefined);
  }

  private persistPendingEdgesForNode(nodeId: string): void {
    const candidateEdges = this.edges().filter((edge) =>
      edge.source === nodeId || edge.target === nodeId
    );
    for (const edge of candidateEdges) {
      const backendId = (edge as EdgeWithData).data?.['backendId'] as number | undefined;
      if (backendId !== undefined) continue;
      this.persistCreateEdge(edge);
    }
  }

  private persistPositionUpdates(posChanges: NodePositionChange[]): void {
    if (this.graphId === null) return;
    for (const change of posChanges) {
      const node = this.nodes().find((n) => n.id === change.id) as NodeWithData | undefined;
      const backendId = node?.data?.['backendId'] as number | undefined;
      if (backendId === undefined) continue;
      void this.api.updateNode(backendId, { position: change.point }).catch(() => undefined);
    }
  }

  private resetGraphInBackend(): void {
    if (this.graphId !== null) {
      void this.api.deleteGraph(this.graphId).catch(() => undefined);
    }
    void this.api.createGraph({
      name: `${this.architecture}-graph`,
      architecture: this.architecture,
      metadata: null,
    }).then((created) => {
      this.setGraphId(created.graph_id);
    }).catch(() => undefined);
  }

  private storageKey(): string {
    return `fedsim.graphId.${this.architecture}`;
  }

  protected normalizeNodeId(newNode: Node): Node {
    const data = { ...((newNode as NodeWithData).data ?? {}) };
    const config = { ...((data as Record<string, any>)['config'] ?? {}) };
    const configId = typeof (config as Record<string, any>)['id'] === 'string'
      ? ((config as Record<string, any>)['id'] as string).trim()
      : '';
    const existingBaseIds = new Set(
      this.nodes()
        .map((node) => {
          const nodeData = (node as NodeWithData).data as Record<string, any> | undefined;
          const nodeConfig = nodeData ? nodeData['config'] as Record<string, any> | undefined : undefined;
          const nodeConfigId = typeof nodeConfig?.['id'] === 'string' ? nodeConfig['id'] as string : '';
          if (nodeConfigId) return nodeConfigId;
          const rawId = typeof node.id === 'string' ? node.id : '';
          const parts = rawId.split(':');
          return parts.length > 1 ? parts.slice(1).join(':') : rawId;
        })
        .filter((value) => value)
    );
    const typeKey = this.resolveTypeKey(newNode, data);
    const prefix = this.prefixForType(typeKey);

    let finalId: string;
    if (prefix) {
      finalId = this.nextAvailableId(prefix, existingBaseIds);
    } else if (configId && !existingBaseIds.has(configId)) {
      finalId = configId;
    } else if (typeof newNode.id === 'string' && !existingBaseIds.has(newNode.id)) {
      finalId = newNode.id;
    } else {
      finalId = this.nextAvailableId('ND', existingBaseIds);
    }

    (config as Record<string, any>)['id'] = finalId;
    (data as Record<string, any>)['config'] = config;
    const graphTag = this.graphId !== null ? `G${this.graphId}` : 'local';
    const uniqueId = `${graphTag}:${finalId}`;
    return { ...newNode, id: uniqueId, data } as Node;
  }

  protected resolveTypeKey(node: Node, data: Record<string, any>): string | null {
    const explicit = typeof data['type'] === 'string' ? (data['type'] as string) : null;
    if (explicit) return explicit;
    const typeName = (node.type as any)?.name;
    return typeof typeName === 'string' ? typeName : null;
  }

  protected prefixForType(typeKey: string | null): string | null {
    if (!typeKey) return null;
    switch (typeKey) {
      case 'SuperServerNode':
        return 'SS';
      case 'ServerNode':
        return 'SV';
      case 'ClientNode':
        return 'CL';
      default:
        return null;
    }
  }

  protected nextAvailableId(prefix: string, existingIds: Set<string>): string {
    const matcher = new RegExp(`^${prefix}-(\\d+)$`);
    let max = 0;
    for (const id of existingIds) {
      const match = id.match(matcher);
      if (match) {
        const value = Number(match[1]);
        if (Number.isFinite(value) && value > max) {
          max = value;
        }
      }
    }
    let next = max + 1;
    let candidate = this.formatId(prefix, next);
    while (existingIds.has(candidate)) {
      next += 1;
      candidate = this.formatId(prefix, next);
    }
    return candidate;
  }

  private formatId(prefix: string, value: number): string {
    return `${prefix}-${String(value).padStart(2, '0')}`;
  }
}
