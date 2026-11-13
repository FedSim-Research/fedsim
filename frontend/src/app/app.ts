import { Component, inject, ViewChild, computed, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, VflowComponent, StaticEdge as Edge, NodePositionChange, Connection, ConnectionSettings } from 'ngx-vflow';
import { FlowRenderer } from './editor/flow-renderer';
import { NgxSelectoModule } from 'ngx-selecto';
import { Shortcuts } from './editor/shortcuts.directive';
import { SidebarComponent } from './shell/sidebar/sidebar';
import { EdgeMetricsBoxComponent } from './editor/edges/edge-metrics-box/edge-metrics-box';
import { GraphWorkspace } from './editor/graph-workspace.service';
import { GraphPersistenceService } from './editor/graph-persistence.service';
import { MessageService } from 'primeng/api';
import { FrameworkJobsPopupComponent } from './runs/framework-jobs-popup/framework-jobs-popup';
import { DashboardViewComponent } from './runs/dashboard-view/dashboard-view';
import { SimulationRunner } from './runs/simulation-runner.service';
import { SimulationRequest } from './runs/simulation-request';
import { v4 as uuidv4 } from 'uuid';
import { Architecture, isNodeKind, NodeKind } from './domain/topology';
import { createGraphNode } from './editor/nodes/node-factory';
import { NodeDrag } from './editor/node-drag';
import { canConnect, normalizeConnection } from './editor/connection-policy';

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
  private workspace = inject(GraphWorkspace);
  private graphPersistence = inject(GraphPersistenceService);
  private messageService = inject(MessageService);
  private simulationRunner = inject(SimulationRunner);
  public activeMode = signal<Architecture>('hierfl');
  public activeView = signal<workspaceView>('editor');
  public sidebarOpen = signal(true);
  public activeGraph = computed(() => this.workspace.graphFor(this.activeMode()));
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

  public graphIdOf(architecture: Architecture): number | null {
    const graph = this.workspace.graphFor(architecture);
    return graph.getGraphId() ?? graph.loadGraphIdFromStorage();
  }

  private readonly drag = new NodeDrag(
    () => this.activeGraph(),
    () => this.shortcuts?.selectedNodeIds ?? new Set<string>(),
  );

  public connectionSettings: ConnectionSettings = {
    mode: 'loose',
    validator: (connection) => canConnect(this.activeMode(), this.nodes(), this.edges(), connection),
  };

  public ngOnInit(): void {
    for (const architecture of ['spyker', 'hierfl'] as const) {
      void this.graphPersistence.initializeGraph(this.workspace.graphFor(architecture), architecture, false);
    }
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
    const pointer = { x: event.clientX, y: event.clientY };
    const rejection = this.activeGraph().addNode(createGraphNode({
      id: uuidv4(),
      kind: payload.kind,
      architecture: this.activeMode(),
      point: this.flow?.documentPointToFlowPoint(pointer) ?? pointer,
      config: payload.config,
    }));
    if (rejection) {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: rejection });
    }
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
  }

  public handleNodePositionChange(changes: NodePositionChange[]): void {
    this.drag.handle(changes);
  }

  public handleSimulation(request: SimulationRequest): void {
    void this.simulationRunner.run(request);
  }

  public handleGraphDeleted(event: { graphId: number; architecture: Architecture }): void {
    const service = this.workspace.graphFor(event.architecture);
    if (service.getGraphId() === event.graphId) {
      service.detachGraph();
    }
  }

  public async handleGraphSelected(event: { graphId: number; architecture: Architecture }): Promise<void> {
    this.activeMode.set(event.architecture);
    const service = this.workspace.graphFor(event.architecture);
    try {
      await this.graphPersistence.loadGraph(service, event.architecture, event.graphId);
    } catch (error) {
      console.error('Failed to load graph:', error);
    }
  }
}
