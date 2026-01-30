import { Component, inject, ViewChild, computed, signal, OnInit, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, VflowComponent, Node, Edge, NodePositionChange, Connection, ɵConnectionModel as ConnectionModel } from 'ngx-vflow';
import { NgxSelectoModule } from 'ngx-selecto';
import { Shortcuts } from './directives/shortcuts';
import { SidebarComponent } from './components/sidebar.component/sidebar.component';
import { ClientNode } from './components/nodes/client-node/client-node';
import { ServerNode } from './components/nodes/server-node/server-node';
import { SuperServerNode } from './components/nodes/super-server-node/super-server-node';
import { EdgeMetricsBoxComponent } from './components/edges/edge-metrics-box/edge-metrics-box';
import { GraphServiceSpyker } from './services/subservices/graph-service-spyker';
import { GraphServiceHierach } from './services/subservices/graph-service-hierach';
import { GraphPersistenceService } from './services/graph-persistence.service';
import { GraphApiService } from './services/graph-api.service';
import { MessageService } from 'primeng/api';

export type modes = 'spyker' | 'hierfl';

@Component({
  selector: 'app-root',
  standalone: true,
  templateUrl: './app.html',
  styleUrls: ['./app.css'],
  imports: [Vflow, SidebarComponent, CommonModule, Shortcuts, NgxSelectoModule, EdgeMetricsBoxComponent],
})
export class App implements OnInit{
  @ViewChild(VflowComponent) public flow?: VflowComponent;
  @ViewChild(Shortcuts) private shortcuts?: Shortcuts;
  public keyContainer = window;
  protected graphServiceSpyker = inject(GraphServiceSpyker);
  protected graphServiceHierach = inject(GraphServiceHierach);
  private graphPersistence = inject(GraphPersistenceService);
  private graphApi = inject(GraphApiService);
  private cdr = inject(ChangeDetectorRef);
  private messageService = inject(MessageService);
  public activeMode = signal<modes>('hierfl');
  public activeGraph = computed(() => {
    if (this.activeMode() === 'spyker') {
      return this.graphServiceSpyker;
    } else {
      return this.graphServiceHierach;
    }
  });
  public nodes = computed(() => {
    return this.activeGraph().nodes();
  });

  public edges = computed(() => {
    return this.activeGraph().edges();
  });
  private _dragging = false;
  private _lastPosChanges: NodePositionChange[] | null = null;
  public connectionModel = new ConnectionModel({
    mode: 'loose',
    validator: (connection) => this.canConnect(connection),
  });

  public ngOnInit(): void {
    void this.graphPersistence.initializeGraph(this.graphServiceSpyker, 'spyker', false);
    void this.graphPersistence.initializeGraph(this.graphServiceHierach, 'hierfl', false);
  }

  public handleReset() {
    if (this.activeMode()=='hierfl'){
      this.graphServiceHierach.resetGraph();
    } else if (this.activeMode()=='spyker') {
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
          environment: this.activeMode(),
          fromJson: isFromJson,
          selected: false,
        },
      };
      this.activeGraph().addNode(newNode);
      console.log('added new node:', newNode);
    } catch (e) {
      console.log('Catched', e);
    }
  }

 public changeMode(mode: 'spyker' | 'hierfl'): void {
    if (this.activeMode() === mode) return;
    this.activeMode.set(mode);
    console.log("changed mode to:" + mode);
  }

  public undo(){
    this.activeGraph().getGraphHistory().undo();
    this.activeGraph().getGraphHistory().getState();
    this.activeGraph().nodes.set(this.activeGraph().getGraphHistory().getState().nodes);
    this.activeGraph().edges.set(this.activeGraph().getGraphHistory().getState().edges);
  }

  public redo(){
    this.activeGraph().getGraphHistory().redo();
    this.activeGraph().getGraphHistory().getState();
    this.activeGraph().nodes.set(this.activeGraph().getGraphHistory().getState().nodes);
    this.activeGraph().edges.set(this.activeGraph().getGraphHistory().getState().edges);
  }

  public reloadUI(){
    this.activeGraph().nodes.set(this.activeGraph().nodes());
    this.activeGraph().edges.set(this.activeGraph().edges());
  }

  public handleConnect(connection: Connection): void {
    const resolved = this.activeMode() === 'hierfl'
      ? this.normalizeHierConnection(connection)
      : connection;
    const newEdge: Edge = {
      id: crypto.randomUUID(),
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
    this._lastPosChanges = posChanges;
    if (!this._dragging) {
      this._dragging = true;
      const finish = () => {
        this._dragging = false;
        if (this._lastPosChanges) {
          this.activeGraph().updateNodePositions(this._lastPosChanges);
          this.activeGraph().getGraphHistory().saveState({nodes: this.activeGraph().nodes(), edges: this.activeGraph().edges()});
          this._lastPosChanges = null;
        }
      };
      window.addEventListener('pointerup', finish, { once: true });
      window.addEventListener('mouseup', finish, { once: true });
      window.addEventListener('touchend', finish, { once: true });
    }
  }

  private canConnect(connection: Connection): boolean {
    const sourceNode = this.nodes().find(n => n.id === connection.source);
    const targetNode = this.nodes().find(n => n.id === connection.target);
    if (!sourceNode || !targetNode) return false;

    const sourceType = (sourceNode as any).data?.type as string | undefined;
    const targetType = (targetNode as any).data?.type as string | undefined;
    if (!sourceType || !targetType) return false;

    const isHier = this.activeMode() === 'hierfl';
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

    const resolved = isHier ? this.normalizeHierConnection(connection) : connection;

    if (sourceType === 'ClientNode' || targetType === 'ClientNode') {
      const clientId = sourceType === 'ClientNode' ? connection.source : connection.target;
      if (this.edges().some(e => e.source === clientId || e.target === clientId)) {
        return false;
      }
    }

    const involvesSuperAndServer =
      (sourceType === 'SuperServerNode' && targetType === 'ServerNode') ||
      (sourceType === 'ServerNode' && targetType === 'SuperServerNode');
    if (isHier && involvesSuperAndServer && this.edges().some(e => e.source === resolved.source && e.target === resolved.target)) {
      return false;
    }

    const isSpykerServerPair = !isHier && sourceType === 'ServerNode' && targetType === 'ServerNode';
    if (isSpykerServerPair && this.edges().some(e => e.source === connection.source && e.target === connection.target)) {
      return false;
    }

    return true;
  }

  private normalizeHierConnection(connection: Connection): Connection {
    const sourceNode = this.nodes().find(n => n.id === connection.source);
    const targetNode = this.nodes().find(n => n.id === connection.target);
    if (!sourceNode || !targetNode) return connection;
    const sourceType = (sourceNode as any).data?.type as string | undefined;
    const targetType = (targetNode as any).data?.type as string | undefined;
    if (!sourceType || !targetType) return connection;

    if (sourceType === 'ServerNode' && targetType === 'SuperServerNode') {
      return {
        source: connection.target,
        target: connection.source,
        sourceHandle: 'superserver-out',
        targetHandle: 'server-in-top',
      };
    }
    if (sourceType === 'SuperServerNode' && targetType === 'ServerNode') {
      return {
        source: connection.source,
        target: connection.target,
        sourceHandle: 'superserver-out',
        targetHandle: 'server-in-top',
      };
    }
    if (sourceType === 'ClientNode' && targetType === 'ServerNode') {
      return {
        source: connection.target,
        target: connection.source,
        sourceHandle: 'server-out-bottom',
        targetHandle: 'client-in',
      };
    }
    if (sourceType === 'ServerNode' && targetType === 'ClientNode') {
      return {
        source: connection.source,
        target: connection.target,
        sourceHandle: 'server-out-bottom',
        targetHandle: 'client-in',
      };
    }

    return connection;
  }

  public async handleSimulation(payload: {
    mode: 'spyker' | 'hierfl' | 'both';
    trainingConfig: { epochs: number; lr: number };
    simulationSettings: { runTimeLimit: number; outputFilename: string; evaluateModel: boolean };
  }): Promise<void> {
    const runFor = async (architecture: 'spyker' | 'hierfl'): Promise<void> => {
      const service = architecture === 'spyker' ? this.graphServiceSpyker : this.graphServiceHierach;
      const graphId = service.getGraphId() ?? service.loadGraphIdFromStorage();
      if (graphId === null) {
        this.showErrorToast(`No graph available for ${architecture}. Please check if the backend is running.`);
        return;
      }
      try {
        await this.graphApi.startSimulation({
          graph_id: graphId,
          training_config: payload.trainingConfig,
          simulation_settings: {
            run_time_limit: payload.simulationSettings.runTimeLimit,
            output_filename: payload.simulationSettings.outputFilename || null,
            evaluate_model: payload.simulationSettings.evaluateModel,
          },
        });
        this.showSuccessToast(`${architecture} run started.`);
      } catch {
        this.showErrorToast(`Failed to start ${architecture} simulation.`);
      }
    };

    if (payload.mode === 'both') {
      await Promise.all([runFor('spyker'), runFor('hierfl')]);
    } else {
      await runFor(payload.mode);
    }
  }

  private showSuccessToast(message: string) {
    this.messageService.add({
      severity: 'success',
      summary: 'Simulation started',
      detail: message,
    });
  }

  private showErrorToast(message: string) {
    this.messageService.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
    });
  }

  public async handleGraphSelected(event: { graphId: number; architecture: 'spyker' | 'hierfl' }): Promise<void> {
    try {
      // Switch to the selected architecture mode
      this.activeMode.set(event.architecture);

      // Get the graph data from the API
      const graphDetail = await this.graphApi.getGraph(event.graphId);

      // Get the appropriate graph service
      const targetService = event.architecture === 'spyker' 
        ? this.graphServiceSpyker 
        : this.graphServiceHierach;

      // Set the graph ID in the service
      targetService.setGraphId(event.graphId);

      // Convert backend nodes to frontend nodes
      const NODE_TYPE_MAP = {
        ClientNode: ClientNode,
        ServerNode: ServerNode,
        SuperServerNode: SuperServerNode,
      } as const;

      const nodes: Node[] = [];
      const externalByBackendId = new Map<number, string>();

      for (const node of graphDetail.nodes) {
        const nodeType = NODE_TYPE_MAP[node.type as keyof typeof NODE_TYPE_MAP];
        if (!nodeType) {
          continue;
        }
        externalByBackendId.set(node.node_id, node.external_id);
        nodes.push({
          id: node.external_id,
          point: node.position,
          type: nodeType,
          data: {
            type: node.type,
            config: node.config,
            environment: event.architecture,
            fromJson: true,
            selected: false,
            backendId: node.node_id,
          },
        });
      }

      // Convert backend edges to frontend edges
      const edges: Edge[] = [];
      for (const edge of graphDetail.edges) {
        const source = externalByBackendId.get(edge.source_node_id);
        const target = externalByBackendId.get(edge.target_node_id);
        if (!source || !target) {
          continue;
        }
        edges.push({
          id: `${edge.edge_id}`,
          source,
          target,
          reconnectable: true,
          floating: false,
          data: {
            backendId: edge.edge_id,
          },
        });
      }

      // Load the graph into the active service
      targetService.setGraphState(nodes, edges, true);
    } catch (error) {
      console.error('Failed to load graph:', error);
    }
  }
}
