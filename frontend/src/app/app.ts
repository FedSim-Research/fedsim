import { Component, inject, ViewChild, computed, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, VflowComponent, StaticNode as Node, StaticEdge as Edge, NodePositionChange, Connection, ConnectionSettings } from 'ngx-vflow';
import { FlowRenderer } from './editor/flow-renderer';
import { NgxSelectoModule } from 'ngx-selecto';
import { Shortcuts } from './editor/shortcuts.directive';
import { SidebarComponent } from './shell/sidebar/sidebar';
import { EdgeMetricsBoxComponent } from './editor/edges/edge-metrics-box/edge-metrics-box';
import { SpykerGraphService } from './editor/topologies/spyker-graph.service';
import { HierflGraphService } from './editor/topologies/hierfl-graph.service';
import { GraphPersistenceService } from './editor/graph-persistence.service';
import { MessageService } from 'primeng/api';
import { FrameworkJobsPopupComponent } from './runs/framework-jobs-popup/framework-jobs-popup';
import { DashboardViewComponent } from './runs/dashboard-view/dashboard-view';
import { SimulationRunner } from './runs/simulation-runner.service';
import { SimulationRequest } from './runs/simulation-request';
import { v4 as uuidv4 } from 'uuid';
import { Architecture, isNodeKind, NodeKind } from './domain/topology';
import { createGraphNode } from './editor/nodes/node-factory';
import { canConnect, normalizeConnection, orientServerLinks } from './editor/connection-policy';

export type workspaceView = 'editor' | 'dashboard';


@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  imports: [
    Vflow,
    SidebarComponent,
    CommonModule,
    Shortcuts,
    NgxSelectoModule,
    EdgeMetricsBoxComponent,
    FrameworkJobsPopupComponent,
    DashboardViewComponent,
  ],
})
export class App implements OnInit{
  @ViewChild(VflowComponent) public flow?: VflowComponent;
  @ViewChild(Shortcuts) private shortcuts?: Shortcuts;
  public keyContainer = window;
  protected graphServiceSpyker = inject(SpykerGraphService);
  protected graphServiceHierfl = inject(HierflGraphService);
  private graphPersistence = inject(GraphPersistenceService);
  private messageService = inject(MessageService);
  private simulationRunner = inject(SimulationRunner);
  public activeMode = signal<Architecture>('hierfl');
  public activeView = signal<workspaceView>('editor');
  public sidebarOpen = signal(true);
  public activeGraph = computed(() => {
    if (this.activeMode() === 'spyker') {
      return this.graphServiceSpyker;
    } else {
      return this.graphServiceHierfl;
    }
  });
  public nodes = computed(() => {
    return this.activeGraph().nodes();
  });

  public edges = computed(() => {
    return this.activeGraph().edges();
  });

  private readonly renderer = new FlowRenderer();
  public renderNodes = computed(() => this.renderer.nodes(this.nodes()));
  public renderEdges = computed(() => this.renderer.edges(this.edges()));

  public graphEdge(id: string): Edge | undefined {
    return this.edges().find(edge => edge.id === id);
  }

  public hierflGraphId(): number | null {
    return this.graphServiceHierfl.getGraphId() ?? this.graphServiceHierfl.loadGraphIdFromStorage();
  }

  public spykerGraphId(): number | null {
    return this.graphServiceSpyker.getGraphId() ?? this.graphServiceSpyker.loadGraphIdFromStorage();
  }

  private _dragging = false;
  private _dragCooldown = false;

  private _lastPosChanges: NodePositionChange[] | null = null;
  private _dragPrimaryId: string | null = null;

  public connectionSettings: ConnectionSettings = {
    mode: 'loose',
    validator: (connection) => canConnect(this.activeMode(), this.nodes(), this.edges(), connection),
  };

  public ngOnInit(): void {
    void this.graphPersistence.initializeGraph(this.graphServiceSpyker, 'spyker', false);
    void this.graphPersistence.initializeGraph(this.graphServiceHierfl, 'hierfl', false);
  }

  public handleReset(): void {
    this.activeGraph().resetGraph();
  }

  public onDragOver(event: DragEvent) {
    event.preventDefault();
    if (event.dataTransfer) {
      event.dataTransfer.dropEffect = 'copy';
    }
  }

  public onDrop(event: DragEvent): void {
    event.preventDefault();
    const payload = this.readDropPayload(event);
    if (!payload) {
      return;
    }
    if (this.activeMode() === 'spyker' && payload.kind === 'SuperServerNode') {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'No super server is allowed to exist in the Spyker Environment',
      });
      return;
    }
    const pointer = { x: event.clientX, y: event.clientY };
    this.activeGraph().addNode(createGraphNode({
      id: uuidv4(),
      kind: payload.kind,
      architecture: this.activeMode(),
      point: this.flow?.documentPointToFlowPoint(pointer) ?? pointer,
      config: payload.config,
    }));
  }

  /** Reads the node template the sidebar put on the drag, ignoring foreign drops. */
  private readDropPayload(event: DragEvent): { kind: NodeKind; config: Record<string, unknown> } | null {
    try {
      const payload = JSON.parse(event.dataTransfer?.getData('application/json') || 'null');
      if (!isNodeKind(payload?.type)) {
        return null;
      }
      const config = typeof payload.config === 'object' && payload.config !== null ? payload.config : {};
      return { kind: payload.type, config };
    } catch {
      return null;
    }
  }


 public changeMode(mode: Architecture): void {
    if (this.activeMode() === mode) return;
    this.activeMode.set(mode);
    console.log("changed mode to:" + mode);
  }

  public changeView(view: workspaceView): void {
    if (this.activeView() === view) {
      return;
    }
    this.activeView.set(view);
  }

  public onSidebarOpenChange(isOpen: boolean): void {
    this.sidebarOpen.set(isOpen);
  }

  public undo(): void {
    if (this.activeGraph().undo()) {
      this.shortcuts?.clearSelectionState();
    }
  }

  public redo(): void {
    if (this.activeGraph().redo()) {
      this.shortcuts?.clearSelectionState();
    }
  }

  public reloadUI(){
    this.activeGraph().nodes.set(this.activeGraph().nodes());
    this.activeGraph().edges.set(this.activeGraph().edges());
  }

  public handleConnect(connection: Connection): void {
    const resolved = normalizeConnection(this.nodes(), connection);
    const newEdge: Edge = {
      id: uuidv4(),
      source: resolved.source,
      target: resolved.target,
      sourceHandle: resolved.sourceHandle,
      targetHandle: resolved.targetHandle,
      reconnectable: true,
      floating: false,
    };

    this.activeGraph().addEdge(newEdge);
    console.log('added new edge', newEdge);
  }

  public handleNodePositionChange(posChanges: NodePositionChange[]){
    if (!posChanges?.length) return;

    if (this._dragCooldown) return;

    const currentId = posChanges[0].id;

    if (this._dragPrimaryId !== currentId) {
      this._dragPrimaryId = currentId;
    }

    if (!this._dragging) {
      this._dragging = true;
      const dragSessionId = currentId;

      const listeners = new AbortController();
      const finish = () => {
        listeners.abort();
        this._dragging = false;
        this._dragCooldown = true;
        setTimeout(() => {
          this._dragCooldown = false;
        }, 50);

        if (this._dragPrimaryId === dragSessionId) {
          this._dragPrimaryId = null;
        }

        if (this._lastPosChanges) {
          this.activeGraph().updateNodePositions(this._lastPosChanges);
          if (this.activeMode() === 'spyker') {
            const spyker = this.graphServiceSpyker;
            spyker.edges.set(orientServerLinks(spyker.nodes(), spyker.edges()));
          }
          this.activeGraph().getGraphHistory().saveState({nodes: this.activeGraph().nodes(), edges: this.activeGraph().edges()});
          this._lastPosChanges = null;
        }
      };

      // Whichever end event fires first finishes the drag and removes the others.
      for (const type of ['pointerup', 'pointercancel', 'mouseup', 'touchend', 'touchcancel']) {
        window.addEventListener(type, finish, { signal: listeners.signal });
      }
    }

    const expandedChanges = this.expandSelectedNodeChanges(posChanges);
    this.previewNodePositionChanges(expandedChanges);
    this._lastPosChanges = expandedChanges;
  }

  private expandSelectedNodeChanges(posChanges: NodePositionChange[]): NodePositionChange[] {
    const selection = this.shortcuts?.selectedNodeIds;
    if (!selection || selection.size <= 1) {
      return posChanges;
    }
    const nodes = this.activeGraph().nodes();
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const primaryChange = posChanges[0];
    if (!primaryChange) {
      return posChanges;
    }
    if (!selection.has(primaryChange.id)) {
      return posChanges;
    }
    const primaryNode = nodeMap.get(primaryChange.id);
    if (!primaryNode) {
      return posChanges;
    }
    const basePoint = primaryNode.point ?? { x: 0, y: 0 };
    const dx = primaryChange.point.x - basePoint.x;
    const dy = primaryChange.point.y - basePoint.y;
    if (dx === 0 && dy === 0) {
      return posChanges;
    }

    const alreadyChanged = new Set(posChanges.map((change) => change.id));
    const additions: NodePositionChange[] = [];
    for (const id of selection) {
      if (alreadyChanged.has(id)) {
        continue;
      }
      const node = nodeMap.get(id);
      if (!node) {
        continue;
      }
      const point = node.point ?? { x: 0, y: 0 };
      additions.push({
        type: 'position',
        id,
        point: {
          x: point.x + dx,
          y: point.y + dy,
        },
      });
      alreadyChanged.add(id);
    }

    if (!additions.length) {
      return posChanges;
    }
    return [...posChanges, ...additions];
  }

  private previewNodePositionChanges(posChanges: NodePositionChange[]): void {
    const changeMap = new Map(posChanges.map((change) => [change.id, change.point]));
    const currentNodes = this.activeGraph().nodes();

    const updatedNodes = currentNodes.map((node) => {
      const nextPoint = changeMap.get(node.id);
      if (!nextPoint) {
        return node;
      }

      if (node.id === this._dragPrimaryId) {
        (node as any).point = nextPoint;
        return node;
      }

      return {
        ...node,
        point: nextPoint,
      } as Node;
    });

    this.activeGraph().nodes.set([...updatedNodes]);
  }

  public handleSimulation(request: SimulationRequest): void {
    void this.simulationRunner.run(request);
  }

  public handleGraphDeleted(event: { graphId: number; architecture: Architecture }): void {
    const service = event.architecture === 'spyker' ? this.graphServiceSpyker : this.graphServiceHierfl;
    if (service.getGraphId() === event.graphId) {
      service.detachGraph();
    }
  }

  public async handleGraphSelected(event: { graphId: number; architecture: Architecture }): Promise<void> {
    this.activeMode.set(event.architecture);
    const service = event.architecture === 'spyker' ? this.graphServiceSpyker : this.graphServiceHierfl;
    try {
      await this.graphPersistence.loadGraph(service, event.architecture, event.graphId);
    } catch (error) {
      console.error('Failed to load graph:', error);
    }
  }
}
