import { Component, DestroyRef, HostListener, ViewChild, AfterViewInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, VflowComponent, Node, Edge, NodePositionChange, Connection, ɵConnectionModel as ConnectionModel } from 'ngx-vflow';
import { SidebarComponent } from './components/sidebar.component/sidebar.component';
import { ClientNode } from './components/nodes/client-node/client-node';
import { ServerNode } from './components/nodes/server-node/server-node';
import { SuperServerNode } from './components/nodes/super-server-node/super-server-node';
import { NodeDeleteUiService } from './services/node-delete-ui.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  imports: [Vflow, SidebarComponent, CommonModule],
})
export class App implements AfterViewInit {
  @ViewChild(VflowComponent) private flow?: VflowComponent;

  public activeMode: 'spyker' | 'hierfl' = 'hierfl';
  public nodes: Node[] = [];
  public edges: Edge[] = [];
  public connectionModel = new ConnectionModel({
    mode: 'loose',
    validator: (connection) => this.canConnect(connection),
  });

  private alreadyHasSuperServer = false;
  private pendingNodePositions = new Map<string, { x: number; y: number }>();
  private graphsByMode: Record<'spyker' | 'hierfl', { nodes: Node[]; edges: Edge[] }> = {
    spyker: { nodes: [], edges: [] },
    hierfl: { nodes: [], edges: [] },
  };
  private historyByMode: Record<'spyker' | 'hierfl', Node[][]> = {
    spyker: [],
    hierfl: [],
  };
  private historyIndexByMode: Record<'spyker' | 'hierfl', number> = {
    spyker: 0,
    hierfl: 0,
  };
  private selectedEdgeIds = new Set<string>();

  constructor(
    private nodeDeleteUi: NodeDeleteUiService,
    private destroyRef: DestroyRef
  ) {
    this.saveHistory();
    this.nodeDeleteUi.deleteRequests$
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((nodeId) => this.deleteNodeById(nodeId));
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
  }

  private saveHistory() {
    const history = this.historyByMode[this.activeMode];
    const index = this.historyIndexByMode[this.activeMode];

    if (index < history.length - 1) {
      this.historyByMode[this.activeMode] = history.slice(0, index + 1);
    }

    this.historyByMode[this.activeMode].push([...this.nodes]);
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
      this.nodes = [...history[this.historyIndexByMode[this.activeMode]]];
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.edges = this.normalizeEdges([...this.graphsByMode[this.activeMode].edges]);
      this.graphsByMode[this.activeMode].edges = this.edges;
      this.updateSuperServerStatus();
    }
  }

  public redo() {
    const history = this.historyByMode[this.activeMode];
    if (this.historyIndexByMode[this.activeMode] < history.length - 1) {
      this.historyIndexByMode[this.activeMode] += 1;
      this.nodes = [...history[this.historyIndexByMode[this.activeMode]]];
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.edges = this.normalizeEdges([...this.graphsByMode[this.activeMode].edges]);
      this.graphsByMode[this.activeMode].edges = this.edges;
      this.updateSuperServerStatus();
    }
  }

  private updateSuperServerStatus() {
    this.alreadyHasSuperServer = this.nodes.some(n => (n as any).data?.type === 'SuperServerNode');
  }

  private normalizeEdges(edges: Edge[]): Edge[] {
    // Keep edges anchored to their declared handles instead of auto-floating
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
  public flushNodePositionChanges(): void {
    if (!this.pendingNodePositions.size) return;
    const changesById = new Map(this.pendingNodePositions);
    this.pendingNodePositions.clear();
    this.nodes = this.nodes.map(node => {
      const point = changesById.get(node.id);
      return point ? { ...node, point } : node;
    });
    this.graphsByMode[this.activeMode].nodes = this.nodes;
  }

  private deleteNodeById(nodeId: string): void {
    if (!this.nodes.some(node => node.id === nodeId)) return;
    this.nodes = this.nodes.filter(node => node.id !== nodeId);
    this.edges = this.edges.filter(edge => edge.source !== nodeId && edge.target !== nodeId);
    this.graphsByMode[this.activeMode].nodes = this.nodes;
    this.graphsByMode[this.activeMode].edges = this.edges;
    this.updateSuperServerStatus();
    this.saveHistory();
  }

  public handleReset() {
    this.nodes = [];
    this.edges = [];
    this.alreadyHasSuperServer = false;
    this.graphsByMode[this.activeMode] = { nodes: [], edges: [] };
    this.saveHistory();
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
          if (this.alreadyHasSuperServer) {
            console.warn('Block: SuperServer already exists (found by text content).');
            event.preventDefault();
            event.stopPropagation();
            return;
          } else {
            this.alreadyHasSuperServer = true;
          }
          break;
        default:
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
        },
      };

      this.nodes = [...this.nodes, newNode];
      this.graphsByMode[this.activeMode].nodes = this.nodes;
      this.graphsByMode[this.activeMode].edges = this.edges;
      this.saveHistory();
    } catch (e) {
      console.log('Catched', e);
    }
  }

  public onModeChange(mode: 'spyker' | 'hierfl'): void {
    if (this.activeMode === mode) return;

    this.graphsByMode[this.activeMode] = {
      nodes: this.nodes,
      edges: this.edges,
    };

    this.activeMode = mode;
    this.nodes = this.graphsByMode[mode].nodes;
    this.edges = this.normalizeEdges(this.graphsByMode[mode].edges);
    this.graphsByMode[mode].edges = this.edges;
    this.selectedEdgeIds.clear();

    if (this.historyByMode[mode].length === 0) {
      this.historyByMode[mode] = [[...this.nodes]];
      this.historyIndexByMode[mode] = 0;
    }

    this.updateSuperServerStatus();
  }

  @HostListener('window:keydown', ['$event'])
  public onKeyDown(event: KeyboardEvent): void {
    if (event.key !== 'Delete' && event.key !== 'Backspace') return;
    if (!this.selectedEdgeIds.size) return;
    event.preventDefault();
    const ids = new Set(this.selectedEdgeIds);
    this.edges = this.edges.filter(e => !ids.has(e.id));
    this.graphsByMode[this.activeMode].edges = this.edges;
    this.selectedEdgeIds.clear();
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

    // Clients are limited to a single edge total (in or out)
    if ((sourceType === 'ClientNode' || targetType === 'ClientNode') && this.edges.some(e => e.source === connection.source || e.target === connection.source || e.source === connection.target || e.target === connection.target)) {
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
  }
}