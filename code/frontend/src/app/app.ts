import { Component, DestroyRef, inject, HostListener, ViewChild, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, VflowComponent, Node, Edge, NodePositionChange, Connection, ɵConnectionModel as ConnectionModel } from 'ngx-vflow';
import { SidebarComponent } from './components/sidebar.component/sidebar.component';
import { ClientNode } from './components/nodes/client-node/client-node';
import { ServerNode } from './components/nodes/server-node/server-node';
import { SuperServerNode } from './components/nodes/super-server-node/super-server-node';
import { GraphServiceSpyker } from './services/subservices/graph-service-spyker';
import { GraphHistoryServiceSpyker } from './services/subservices/graph-history-service-spyker';
import { GraphServiceHierach } from './services/subservices/graph-service-hierach';
import { GraphHistoryServiceHierach } from './services/subservices/graph-history-service-hierach';


@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  imports: [Vflow, SidebarComponent, CommonModule],
})
export class App implements AfterViewInit{
  @ViewChild(VflowComponent) private flow?: VflowComponent;
  protected graphServiceSpyker = inject(GraphServiceSpyker);
  protected graphHistorySpyker = inject(GraphHistoryServiceSpyker);
  protected graphServiceHierach = inject(GraphServiceHierach);
  protected graphHistoryHierach = inject(GraphHistoryServiceHierach);
  public nodes: Node[] = [];
  public edges: Edge[] = [];
  public activeMode: ('spyker' | 'hierfl') = 'hierfl';
  private pendingNodePositions = new Map<string, { x: number; y: number }>();
  private selectedNodeIds = new Set<string>();
  private selectedEdgeIds = new Set<string>();
  private copyBuffer: Node[] = [];
  public selectionBox = { visible: false, left: 0, top: 0, width: 0, height: 0 };
  private dragOrigin: { x: number; y: number } | null = null;
  public connectionModel = new ConnectionModel({
    mode: 'loose',
    validator: (connection) => this.canConnect(connection),
  });


  public ngAfterViewInit(): void {
    this.flow?.edgesChange$?.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(changes => {
      for (const change of changes) {
        if ((change as any).type === 'select') {
          const selected = (change as any).selected as boolean;
          if (selected) {
            this.selectedEdgeIds.add((change as any).id);
          } else {
            this.selectedEdgeIds.delete((change as any).id);
          }
        }
      }
    });

    const clearSelectionOnClick = (event: MouseEvent) => {
      if (event.ctrlKey || event.metaKey) return;
      if (event.button !== 0 && event.button !== 2) return;
      if (!this.selectedNodeIds.size) return;
      this.clearNodeSelection();
    };

    window.addEventListener('mousedown', clearSelectionOnClick, true);
    this.destroyRef.onDestroy(() => {
      window.removeEventListener('mousedown', clearSelectionOnClick, true);
    });

    window.addEventListener('node-ctrl-click', (event: Event) => {
      const id = (event as CustomEvent)?.detail?.id as string | undefined;
      if (!id) return;
      this.toggleNodeSelection(id);
    });
  }

  public ngAfterViewInit(): void {
    this.flow?.edgesChange$?.pipe(takeUntilDestroyed(this.destroyRef)).subscribe(changes => {
      for (const change of changes) {
        if ((change as any).type === 'select') {
          const selected = (change as any).selected as boolean;
          if (selected) {
            this.selectedEdgeIds.add((change as any).id);
          } else {
            this.selectedEdgeIds.delete((change as any).id);
          }
        }
      }
    });

    const clearSelectionOnClick = (event: MouseEvent) => {
      if (event.ctrlKey || event.metaKey) return;
      if (event.button !== 0 && event.button !== 2) return;
      if (!this.selectedNodeIds.size) return;
      this.clearNodeSelection();
    };

    window.addEventListener('mousedown', clearSelectionOnClick, true);
    this.destroyRef.onDestroy(() => {
      window.removeEventListener('mousedown', clearSelectionOnClick, true);
    });

    window.addEventListener('node-ctrl-click', (event: Event) => {
      const id = (event as CustomEvent)?.detail?.id as string | undefined;
      if (!id) return;
      this.toggleNodeSelection(id);
    });
  }

  private saveHistory(opts: { flush?: boolean } = {}) {
    const { flush = true } = opts;
    if (flush) {
      this.flushNodePositionChanges(false);
    }

    const history = this.historyByMode[this.activeMode];
    const index = this.historyIndexByMode[this.activeMode];

    if (index < history.length - 1) {
      this.historyByMode[this.activeMode] = history.slice(0, index + 1);
    }

    const nodeSnapshot = this.nodes.map(n => ({
      ...n,
      point: n.point ? { ...n.point } : n.point,
      data: { ...(n as any).data },
    }));
    const edgeSnapshot = this.edges.map(e => ({ ...e }));

    this.historyByMode[this.activeMode].push({
      nodes: nodeSnapshot,
      edges: edgeSnapshot,
    });
    this.historyIndexByMode[this.activeMode] += 1;

    if (this.historyByMode[this.activeMode].length > 20) {
      this.historyByMode[this.activeMode].shift();
      this.historyIndexByMode[this.activeMode] -= 1;
    }
  }

  public undo() {
    if (this.historyIndexByMode[this.activeMode] > 0) {
      this.historyIndexByMode[this.activeMode] -= 1;
      const history = this.historyByMode[this.activeMode];
      const snapshot = history[this.historyIndexByMode[this.activeMode]];
      this.nodes = [...snapshot.nodes];
      this.edges = this.normalizeEdges([...snapshot.edges]);
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.graphsByMode[this.activeMode].edges = this.edges;
      this.updateSuperServerStatus();
    }
  }

  public redo() {
    const history = this.historyByMode[this.activeMode];
    if (this.historyIndexByMode[this.activeMode] < history.length - 1) {
      this.historyIndexByMode[this.activeMode] += 1;
      const snapshot = history[this.historyIndexByMode[this.activeMode]];
      this.nodes = [...snapshot.nodes];
      this.edges = this.normalizeEdges([...snapshot.edges]);
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.graphsByMode[this.activeMode].edges = this.edges;
      this.updateSuperServerStatus();
    }
  }

  private updateSuperServerStatus() {
    this.alreadyHasSuperServer = this.nodes.some(n => (n as any).data?.type === 'SuperServerNode');
  }

  private normalizeEdges(edges: Edge[]): Edge[] {
    return edges.map(edge => ({ ...edge, floating: false }));
  }

  public onNodePositionChange(changes: NodePositionChange[]): void {
    if (!changes?.length) return;
    for (const change of changes) {
      this.pendingNodePositions.set(change.id, change.point);
    }
  }

  @HostListener('window:mouseup')
  @HostListener('window:touchend')
  public flushNodePositionChanges(recordHistory = true): void {
    if (!this.pendingNodePositions.size) return;
    const changesById = new Map(this.pendingNodePositions);
    this.pendingNodePositions.clear();
    this.nodes = this.nodes.map(node => {
      const point = changesById.get(node.id);
      return point ? { ...node, point } : node;
    });
    this.graphsByMode[this.activeMode].nodes = this.nodes;

    if (recordHistory) {
      this.saveHistory({ flush: false });
    }
  }

  private deleteNodeById(nodeId: string): void {
    if (!this.nodes.some(node => node.id === nodeId)) return;
    this.nodes = this.nodes.filter(node => node.id !== nodeId);
    this.edges = this.edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId);
    this.selectedNodeIds.delete(nodeId);
    this.graphsByMode[this.activeMode].nodes = this.nodes;
    this.graphsByMode[this.activeMode].edges = this.edges;
    this.updateSuperServerStatus();
    this.saveHistory();
    this.applySelection(new Set(this.selectedNodeIds));
  }

  public handleReset() {
    this.nodes = [];
    this.edges = [];
    if (this.activeMode=='hierfl'){
      this.graphServiceHierach.resetGraph();
    } else if (this.activeMode=='spyker') {
      this.graphServiceSpyker.resetGraph();
    }
  }

  public onDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  public onDrop(event: DragEvent) {
    event.preventDefault();
    const rawData = event.dataTransfer?.getData('application/json');
    if (!rawData) return;
    try {
      const payload = JSON.parse(rawData);
      const isFromJson = payload?.origin === 'json' || payload?.fromJson === true;
      const flowPoint = this.flow?.documentPointToFlowPoint({
        x: event.clientX,
        y: event.clientY,
      });
      const mousePosition = flowPoint ?? {
        x: event.clientX,
        y: event.clientY,
      };

      let nodeType;
      switch (payload.type.toString()) {
        case 'ClientNode':
          nodeType = ClientNode;
          break;
        case 'ServerNode':
          nodeType = ServerNode;
          break;
        case 'SuperServerNode':
          nodeType = SuperServerNode;
          break;
        default:
          console.log('this is the default case');
          return;
      }

      const newNode: Node = {
        id: crypto.randomUUID(),
        point: mousePosition,
        type: nodeType,
        data: {
          type: payload.type,
          config: payload.config,
          environment: this.activeMode,
          fromJson: isFromJson,
          selected: false,
        },
      };

      this.nodes = [...this.nodes, newNode];
      if (this.activeMode=="hierfl"){
        console.log("Hierach and added node")
        this.graphServiceHierach.addNode(newNode);
        this.graphHistoryHierach.saveState({nodes: this.nodes, edges: this.edges});
      } else {
        this.graphServiceSpyker.addNode(newNode);
        this.graphHistorySpyker.saveState({nodes: this.nodes, edges: this.edges});
      }
      console.log('added new node:', newNode);
    } catch (e) {
      console.log('Catched', e);
    }
  }

public onModeChange(mode: 'spyker' | 'hierfl'): void {
    if (this.activeMode === mode) return;
    this.activeMode = mode;
    if (this.activeMode == 'spyker'){
      console.log("changed mode to spyker");
      this.nodes = this.graphServiceSpyker.nodes();
      this.edges = this.graphServiceSpyker.edges();
    }
    if (this.activeMode == 'hierfl'){
      console.log("changed mode to hierarch")
      this.nodes = this.graphServiceHierach.nodes();
      this.edges = this.graphServiceHierach.edges();
    }
  }

  public undo(){
    if (this.activeMode == 'spyker'){
      this.graphHistorySpyker.undo();
      this.nodes = this.graphHistorySpyker.getNodes();
      this.edges = this.graphHistorySpyker.getEdges();
    }
    if (this.activeMode == 'hierfl'){
      this.graphHistoryHierach.undo();
      this.nodes = this.graphHistoryHierach.getNodes();
      this.edges = this.graphHistoryHierach.getEdges();
    }
  }

  public redo(){
    if (this.activeMode == 'spyker'){
      this.graphHistorySpyker.redo();
      this.nodes = this.graphHistorySpyker.getNodes();
      this.edges = this.graphHistorySpyker.getEdges();
    }
    if (this.activeMode == 'hierfl'){
      this.graphHistoryHierach.redo();
      this.nodes = this.graphHistoryHierach.getNodes();
      this.edges = this.graphHistoryHierach.getEdges();
    }
  }

  public exportcurrentGraph() { 
    let currentNodes = this.nodes.toString;
    let graph: JSON = JSON.parse()
  }

  @HostListener('window:keydown', ['$event'])
  public onKeyDown(event: KeyboardEvent): void {
    if (event.ctrlKey || event.metaKey) {
      if (event.key.toLowerCase() === 'c') {
        event.preventDefault();
        this.copySelectedNodes();
        return;
      }
      if (event.key.toLowerCase() === 'v') {
        event.preventDefault();
        this.pasteCopiedNodes();
        return;
      }
    }

    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (!this.selectedEdgeIds.size) return;
      event.preventDefault();
      const ids = new Set(this.selectedEdgeIds);
      this.edges = this.normalizeEdges(this.edges.filter(e => !ids.has(e.id)));
      this.graphsByMode[this.activeMode].edges = this.edges;
      this.saveHistory();
      this.selectedEdgeIds.clear();
    }
  }

  private canConnect(connection: Connection): boolean {
    const sourceNode = this.nodes.find(n => n.id === connection.source);
    const targetNode = this.nodes.find(n => n.id === connection.target);
    if (!sourceNode || !targetNode) return false;

    const sourceType = (sourceNode as any).data?.type as string | undefined;
    const targetType = (targetNode as any).data?.type as string | undefined;
    if (!sourceType || !targetType) return false;

    const isHier = this.activeMode === 'hierfl';
    const pair = `${sourceType}->${targetType}`;
    const validPairs = isHier
      ? new Set([
          'SuperServerNode->ServerNode',
          'ServerNode->SuperServerNode',
          'ServerNode->ClientNode',
          'ClientNode->ServerNode',
        ])
      : new Set([
          'ServerNode->ServerNode',
          'ServerNode->ClientNode',
          'ClientNode->ServerNode',
        ]);
    const valid = validPairs.has(pair);

    if (!valid) return false;

    if (sourceType === 'ClientNode' || targetType === 'ClientNode') {
      const clientId = sourceType === 'ClientNode' ? connection.source : connection.target;
      if (this.edges.some(e => e.source === clientId || e.target === clientId)) {
        return false;
      }
    }

    const involvesSuperAndServer =
      (sourceType === 'SuperServerNode' && targetType === 'ServerNode') ||
      (sourceType === 'ServerNode' && targetType === 'SuperServerNode');
    if (isHier && involvesSuperAndServer && this.hasEdgeBetween(connection.source, connection.target)) {
      return false;
    }

    const isSpykerServerPair = !isHier && sourceType === 'ServerNode' && targetType === 'ServerNode';
    if (isSpykerServerPair && this.hasEdgeBetween(connection.source, connection.target)) {
      return false;
    }

    return true;
  }

  public handleConnect(connection: Connection): void {
    if (!this.canConnect(connection)) return;

    const newEdge: Edge = {
      id: crypto.randomUUID(),
      source: connection.source,
      target: connection.target,
      sourceHandle: connection.sourceHandle,
      targetHandle: connection.targetHandle,
      reconnectable: true,
      floating: false,
    };

    this.edges = [...this.edges, newEdge];
    this.graphsByMode[this.activeMode].edges = this.edges;
    this.saveHistory();
  }

  private hasEdgeBetween(aId: string, bId: string): boolean {
    return this.edges.some(e =>
      (e.source === aId && e.target === bId) || (e.source === bId && e.target === aId)
    );
  }

  private autoConnectSpykerServers(newNode: Node, isFromJson: boolean): void {
    if (isFromJson) return;
    if (this.activeMode !== 'spyker') return;
    const type = (newNode as any).data?.type;
    if (type !== 'ServerNode') return;

    const serverNodes = this.nodes.filter(n =>
      n.id !== newNode.id &&
      (n as any).data?.type === 'ServerNode' &&
      !(n as any).data?.fromJson
    );

    const freshEdges: Edge[] = [];
    for (const server of serverNodes) {
      if (this.hasEdgeBetween(server.id, newNode.id)) continue;
      const [source, target] = server.id < newNode.id ? [server, newNode] : [newNode, server];
      freshEdges.push({
        id: crypto.randomUUID(),
        source: source.id,
        target: target.id,
        sourceHandle: 'server-out',
        targetHandle: 'server-in',
        reconnectable: true,
        floating: false,
      });
    }

    if (freshEdges.length) {
      this.edges = this.normalizeEdges([...this.edges, ...freshEdges]);
      this.graphsByMode[this.activeMode].edges = this.edges;
    }
  }

  private toggleNodeSelection(id: string): void {
    const next = new Set(this.selectedNodeIds);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    this.applySelection(next);
  }

  private clearNodeSelection(): void {
    if (!this.selectedNodeIds.size) return;
    this.applySelection(new Set());
  }

  private applySelection(ids: Set<string>): void {
    if (this.pendingNodePositions.size) {
      this.flushNodePositionChanges(); 
    }
    this.selectedNodeIds = ids;
    this.nodes = this.nodes.map(node => ({
      ...node,
      data: { ...(node as any).data, selected: ids.has(node.id) },
    }));
    this.graphsByMode[this.activeMode].nodes = this.nodes;
  }

  private copySelectedNodes(): void {
    if (this.pendingNodePositions.size) {
      this.flushNodePositionChanges();
    }
    const selected = this.nodes.filter(n => this.selectedNodeIds.has(n.id));
    this.copyBuffer = selected.map(n => ({
      ...n,
      point: { ...this.resolveNodePoint(n) },
      data: { ...(n as any).data },
    }));
  }

  private pasteCopiedNodes(): void {
    if (!this.copyBuffer.length) return;
    const offsetStep = 30;
    const baseOffset = { x: 30, y: 30 };
    const pasted: Node[] = [];

    for (const n of this.copyBuffer) {
      let candidate = {
        x: (n.point?.x ?? 0) + baseOffset.x,
        y: (n.point?.y ?? 0) + baseOffset.y,
      };

      let attempts = 0;
      while (attempts < 10 && this.nodes.concat(pasted).some(existing => {
        const p = existing.point;
        if (!p) return false;
        const dx = Math.abs((p.x ?? 0) - candidate.x);
        const dy = Math.abs((p.y ?? 0) - candidate.y);
        return dx < 20 && dy < 20;
      })) {
        candidate = { x: candidate.x + offsetStep, y: candidate.y + offsetStep };
        attempts += 1;
      }

      pasted.push({
        ...n,
        id: crypto.randomUUID(),
        point: candidate,
        data: { ...(n as any).data, environment: this.activeMode, selected: false, fromJson: false },
      } as Node);
    }

    this.nodes = [...this.nodes, ...pasted];
    this.graphsByMode[this.activeMode].nodes = this.nodes;
    this.clearNodeSelection();
    this.saveHistory();
  }

  private resolveNodePoint(node: Node): { x: number; y: number } {
    if (node.point?.x !== undefined && node.point?.y !== undefined) {
      return { x: node.point.x, y: node.point.y };
    }

    const el = document.querySelector(`.node-wrapper[data-id="${node.id}"]`) as HTMLElement | null;
    const root = document.querySelector('.root-svg') as HTMLElement | null;
    if (el && root) {
      const rect = el.getBoundingClientRect();
      const rootRect = root.getBoundingClientRect();

      return {
        x: rect.left - rootRect.left + rect.width / 2,
        y: rect.top - rootRect.top + rect.height / 2,
      };
    }

    return { x: 0, y: 0 };
  }

  public onCanvasMouseDown(event: MouseEvent): void {
    if (event.button !== 0 && event.button !== 2) return;
    const target = event.target as HTMLElement;


    if (target.closest('app-sidebar')) return;
    if (target.closest('.vflow-node') || target.closest('.node-wrapper')) return;

    const inFlow = target.closest('.root-svg');
    if (!inFlow) return;

    if (event.button === 2) {
      event.preventDefault(); 
    }

    this.dragOrigin = { x: event.clientX, y: event.clientY };
    this.selectionBox = { visible: true, left: event.clientX, top: event.clientY, width: 0, height: 0 };
  }

  @HostListener('window:mousemove', ['$event'])
  public onMouseMove(event: MouseEvent): void {
    if (!this.selectionBox.visible || !this.dragOrigin) return;
    const x1 = this.dragOrigin.x;
    const y1 = this.dragOrigin.y;
    const x2 = event.clientX;
    const y2 = event.clientY;
    const left = Math.min(x1, x2);
    const top = Math.min(y1, y2);
    const width = Math.abs(x1 - x2);
    const height = Math.abs(y1 - y2);
    this.selectionBox = { visible: true, left, top, width, height };
  }

  @HostListener('window:mouseup', ['$event'])
  public onMouseUp(event: MouseEvent): void {
    if (!this.selectionBox.visible || !this.dragOrigin) return;
    const box = this.selectionBox;
    this.selectionBox = { visible: false, left: 0, top: 0, width: 0, height: 0 };
    this.dragOrigin = null;

    if (box.width === 0 && box.height === 0) return;

    const selected = new Set<string>();
    const elements = Array.from(document.querySelectorAll('.node-wrapper')) as HTMLElement[];
    for (const el of elements) {
      const rect = el.getBoundingClientRect();
      const intersects =
        rect.left < box.left + box.width &&
        rect.left + rect.width > box.left &&
        rect.top < box.top + box.height &&
        rect.top + rect.height > box.top;
      if (intersects) {
        const id = el.dataset['id'] || el.getAttribute('data-id') || el.id;
        if (id) selected.add(id);
      }
    }
    this.applySelection(selected);
  }

  @HostListener('window:mousedown', ['$event'])
  public onAnyMouseDown(event: MouseEvent): void {
    if (event.ctrlKey || event.metaKey) return;
    if (event.button !== 0 && event.button !== 2) return;
    if (!this.selectedNodeIds.size) return;
    this.clearNodeSelection();
  }

  @HostListener('window:contextmenu', ['$event'])
  public onContextMenu(event: MouseEvent): void {
    if (this.selectionBox.visible) {
      event.preventDefault();
    }
  }
}
