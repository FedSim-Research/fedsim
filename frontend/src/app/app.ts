import { Component, inject, ViewChild, computed, signal, OnInit } from '@angular/core';
import { CommonModule } from '@angular/common';
import { Vflow, VflowComponent, StaticNode as Node, StaticEdge as Edge, NodePositionChange, Connection, ConnectionSettings } from 'ngx-vflow';
import { FlowRenderer } from './editor/flow-renderer';
import { NgxSelectoModule } from 'ngx-selecto';
import { Shortcuts } from './editor/shortcuts.directive';
import { SidebarComponent } from './shell/sidebar/sidebar';
import { ClientNode } from './editor/nodes/client-node/client-node';
import { ServerNode } from './editor/nodes/server-node/server-node';
import { SuperServerNode } from './editor/nodes/super-server-node/super-server-node';
import { EdgeMetricsBoxComponent } from './editor/edges/edge-metrics-box/edge-metrics-box';
import { SpykerGraphService } from './editor/topologies/spyker-graph.service';
import { HierflGraphService } from './editor/topologies/hierfl-graph.service';
import { GraphPersistenceService } from './editor/graph-persistence.service';
import { GraphApiService, SimulationRunResponse } from './api/graph-api.service';
import { GraphValidatorService } from './editor/graph-validator.service';
import { MessageService } from 'primeng/api';
import { FrameworkJobsPopupComponent } from './runs/framework-jobs-popup/framework-jobs-popup';
import { FrameworkJobsService } from './runs/framework-jobs.service';
import { DashboardViewComponent } from './runs/dashboard-view/dashboard-view';
import { v4 as uuidv4 } from 'uuid';
import { Architecture } from './domain/topology';
import { canLink } from './domain/link-rules';

export type workspaceView = 'editor' | 'dashboard';

const RUN_STATUS_POLL_MS = 2000;
/** Consecutive status request failures tolerated before a run is reported as lost. */
const MAX_FAILED_STATUS_POLLS = 5;

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
  private graphApi = inject(GraphApiService);
  private graphValidator = inject(GraphValidatorService);
  private messageService = inject(MessageService);
  private frameworkJobs = inject(FrameworkJobsService);
  public activeMode = signal<Architecture>('hierfl');
  public activeView = signal<workspaceView>('editor');
  public sidebarOpen = signal(true);
  public simulationRunning = signal(false);
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
    validator: (connection) => this.canConnect(connection),
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

  public onDrop(event: DragEvent) {
    event.preventDefault();
    const rawData = event.dataTransfer?.getData('application/json');
    if (!rawData) return;
    try {
      const payload = JSON.parse(rawData);
      const payloadType = payload?.type?.toString();
      if (this.activeMode() === 'spyker' && payloadType === 'SuperServerNode') {
        this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
        return;
      }
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
      switch (payloadType) {
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
        id: uuidv4(),
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
    const resolved = this.activeMode() === 'hierfl'
      ? this.normalizeHierConnection(connection)
      : this.normalizeSpykerConnection(connection);
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
            this.normalizeSpykerServerEdges();
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

  private canConnect(connection: Connection): boolean {
    const sourceNode = this.nodes().find(n => n.id === connection.source);
    const targetNode = this.nodes().find(n => n.id === connection.target);
    if (!sourceNode || !targetNode) return false;

    const sourceType = (sourceNode as any).data?.type as string | undefined;
    const targetType = (targetNode as any).data?.type as string | undefined;
    if (!sourceType || !targetType) return false;

    const isHier = this.activeMode() === 'hierfl';
    const isSpyker = !isHier;

    if (!canLink(this.activeMode(), sourceType, targetType)) return false;


    if (isSpyker && sourceType === 'ServerNode' && targetType === 'ServerNode') {
      if (connection.sourceHandle === 'server-out-bottom' || connection.targetHandle === 'server-out-bottom') {
        return false;
      }
      const alreadyConnected = this.edges().some(e =>
        (e.source === connection.source && e.target === connection.target) ||
        (e.source === connection.target && e.target === connection.source)
      );

      if (alreadyConnected) return false;

      return true;
    }

    const resolved = isHier ? this.normalizeHierConnection(connection) : this.normalizeSpykerConnection(connection);

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

  private normalizeSpykerConnection(connection: Connection): Connection {
    const sourceNode = this.nodes().find(n => n.id === connection.source);
    const targetNode = this.nodes().find(n => n.id === connection.target);
    if (!sourceNode || !targetNode) return connection;
    const sourceType = (sourceNode as any).data?.type as string | undefined;
    const targetType = (targetNode as any).data?.type as string | undefined;
    if (!sourceType || !targetType) return connection;

    if (sourceType === 'ServerNode' && targetType === 'ServerNode') {
      const sourcePoint = (sourceNode as any).point as { x: number; y: number } | undefined;
      const targetPoint = (targetNode as any).point as { x: number; y: number } | undefined;
      if (!sourcePoint || !targetPoint) {
        return connection;
      }

      const sourceIsLeft = sourcePoint.x <= targetPoint.x;
      const leftId = sourceIsLeft ? connection.source : connection.target;
      const rightId = sourceIsLeft ? connection.target : connection.source;

      return {
        source: leftId,
        target: rightId,
        sourceHandle: 'server-out',
        targetHandle: 'server-in',
      };
    }

    if (sourceType === 'ServerNode' && targetType === 'ClientNode') {
      return {
        ...connection,
        sourceHandle: 'server-out-bottom',
        targetHandle: 'client-in',
      };
    }

    if (sourceType === 'ClientNode' && targetType === 'ServerNode') {
      return {
        ...connection,
        source: connection.target,
        target: connection.source,
        sourceHandle: 'server-out-bottom',
        targetHandle: 'client-in',
      };
    }

    return connection;
  }

  private normalizeSpykerServerEdges(): void {
    const nodes = this.graphServiceSpyker.nodes();
    const nodeMap = new Map(nodes.map((node) => [node.id, node]));
    const edges = this.graphServiceSpyker.edges();
    let changed = false;

    const updated = edges.map((edge) => {
      const sourceNode = nodeMap.get(edge.source);
      const targetNode = nodeMap.get(edge.target);
      const sourceType = (sourceNode as any)?.data?.type as string | undefined;
      const targetType = (targetNode as any)?.data?.type as string | undefined;
      if (!sourceNode || !targetNode || sourceType !== 'ServerNode' || targetType !== 'ServerNode') {
        return edge;
      }

      const sourcePoint = (sourceNode as any).point as { x: number; y: number } | undefined;
      const targetPoint = (targetNode as any).point as { x: number; y: number } | undefined;
      if (!sourcePoint || !targetPoint) {
        return edge;
      }

      const sourceIsLeft = sourcePoint.x <= targetPoint.x;
      const leftId = sourceIsLeft ? sourceNode.id : targetNode.id;
      const rightId = sourceIsLeft ? targetNode.id : sourceNode.id;

      const next = {
        ...edge,
        source: leftId,
        target: rightId,
        sourceHandle: 'server-out',
        targetHandle: 'server-in',
      };

      if (
        next.source !== edge.source ||
        next.target !== edge.target ||
        next.sourceHandle !== edge.sourceHandle ||
        next.targetHandle !== edge.targetHandle
      ) {
        changed = true;
      }

      return next;
    });

    if (changed) {
      this.graphServiceSpyker.edges.set(updated);
    }
  }

  public async handleSimulation(payload: {
    mode: Architecture | 'both';
    hierfl: {
      trainingConfig: { epochs: number; lr: number; modelComplexity: number; batchSize?: number };
      simulationSettings: { runTimeLimit: number; evalInterval: number; gpuBudget: number; dataset: string; seedSet: number[]; repetitions: number; outputFilename: string; evaluateModel: boolean };
    };
    spyker: {
      trainingConfig: { epochs: number; lr: number; modelComplexity: number; batchSize?: number };
      simulationSettings: { runTimeLimit: number; evalInterval: number; gpuBudget: number; dataset: string; seedSet: number[]; repetitions: number; idleTokenDelay: number; outputFilename: string; evaluateModel: boolean };
      spykerConfig: {
        decayBeta: number;
        minLearningRate: number;
        hInter: number;
        hIntra: number;
        sigmoidPhi: number;
        serverLearningRate: number;
        tcpRtoDelay: number;
      };
    };
  }): Promise<void> {
    const runFor = async (architecture: Architecture): Promise<void> => {
      const service = architecture === 'spyker' ? this.graphServiceSpyker : this.graphServiceHierfl;
      const graphId = service.getGraphId() ?? service.loadGraphIdFromStorage();
      if (graphId === null) {
        this.showErrorToast(`No graph available for ${architecture}. Please check if the backend is running.`);
        return;
      }
      const archConfig = architecture === 'hierfl' ? payload.hierfl : payload.spyker;
      const validationErrors = this.graphValidator.validateSimulationRequest(
        architecture,
        service.nodes(),
        service.edges(),
        {
          trainingConfig: archConfig.trainingConfig,
          simulationSettings: {
            ...archConfig.simulationSettings,
            evalInterval: archConfig.simulationSettings.evalInterval,
            idleTokenDelay: architecture === 'spyker' ? payload.spyker.simulationSettings.idleTokenDelay : undefined,
          },
          spykerConfig: architecture === 'spyker' ? payload.spyker.spykerConfig : undefined,
        },
      );
      if (validationErrors.length > 0) {
        this.showValidationErrors(architecture, validationErrors);
        return;
      }

      const jobId = this.frameworkJobs.startJob(`${architecture.toUpperCase()} simulation`);
      try {
        this.showInfoToast(`${architecture} simulation queued with ${archConfig.simulationSettings.repetitions} repetitions...`);
        const queuedRun = await this.graphApi.startSimulation({
          graph_id: graphId,
          training_config: {
            epochs: archConfig.trainingConfig.epochs,
            lr: archConfig.trainingConfig.lr,
            model_complexity: archConfig.trainingConfig.modelComplexity,
            batch_size: archConfig.trainingConfig.batchSize,
          },
          simulation_settings: {
            run_time_limit: archConfig.simulationSettings.runTimeLimit,
            eval_interval: archConfig.simulationSettings.evalInterval,
            gpu_budget: archConfig.simulationSettings.gpuBudget,
            dataset: archConfig.simulationSettings.dataset,
            idle_token_delay: architecture === 'spyker' ? payload.spyker.simulationSettings.idleTokenDelay : undefined,
            seed_set: archConfig.simulationSettings.seedSet,
            repetitions: archConfig.simulationSettings.repetitions,
            output_filename: archConfig.simulationSettings.outputFilename || null,
            evaluate_model: archConfig.simulationSettings.evaluateModel,
          },
          spyker_config: architecture === 'spyker'
            ? {
                decay_beta: payload.spyker.spykerConfig.decayBeta,
                min_learning_rate: payload.spyker.spykerConfig.minLearningRate,
                h_inter: payload.spyker.spykerConfig.hInter,
                h_intra: payload.spyker.spykerConfig.hIntra,
                sigmoid_phi: payload.spyker.spykerConfig.sigmoidPhi,
                server_learning_rate: payload.spyker.spykerConfig.serverLearningRate,
                tcp_rto_delay: payload.spyker.spykerConfig.tcpRtoDelay,
              }
            : undefined,
        });

        await this.waitForRunCompletion(queuedRun.run_id, architecture, jobId);
      } catch {
        this.showErrorToast(`Failed to start ${architecture} simulation.`);
        this.frameworkJobs.markFailed(jobId);
      }
    };

    if (payload.mode === 'both') {
      this.simulationRunning.set(true);
      const jobId = this.frameworkJobs.startJob('SPYKER + HIERFL simulation');
      try {
        const hierGraphId = this.graphServiceHierfl.getGraphId() ?? this.graphServiceHierfl.loadGraphIdFromStorage();
        const spykerGraphId = this.graphServiceSpyker.getGraphId() ?? this.graphServiceSpyker.loadGraphIdFromStorage();
        if (hierGraphId === null || spykerGraphId === null) {
          this.showErrorToast('Both HierFL and Spyker graphs must be available.');
          this.frameworkJobs.markFailed(jobId);
          return;
        }

        const hierValidationErrors = this.graphValidator.validateSimulationRequest(
          'hierfl',
          this.graphServiceHierfl.nodes(),
          this.graphServiceHierfl.edges(),
          {
            trainingConfig: payload.hierfl.trainingConfig,
            simulationSettings: payload.hierfl.simulationSettings,
          },
        );
        const spykerValidationErrors = this.graphValidator.validateSimulationRequest(
          'spyker',
          this.graphServiceSpyker.nodes(),
          this.graphServiceSpyker.edges(),
          {
            trainingConfig: payload.spyker.trainingConfig,
            simulationSettings: payload.spyker.simulationSettings,
            spykerConfig: payload.spyker.spykerConfig,
          },
        );
        if (hierValidationErrors.length > 0) {
          this.showValidationErrors('hierfl', hierValidationErrors);
          this.frameworkJobs.markFailed(jobId);
          return;
        }
        if (spykerValidationErrors.length > 0) {
          this.showValidationErrors('spyker', spykerValidationErrors);
          this.frameworkJobs.markFailed(jobId);
          return;
        }
        if (!this.haveMatchingSeedSet(payload.hierfl.simulationSettings.seedSet, payload.spyker.simulationSettings.seedSet)) {
          this.showErrorToast('Combined runs require identical seed sets for HierFL and Spyker.');
          this.frameworkJobs.markFailed(jobId);
          return;
        }

        this.showInfoToast(`Combined simulation queued with ${payload.hierfl.simulationSettings.repetitions} repetitions...`);
        const queuedRun = await this.graphApi.startSimulationBoth({
          hierfl: {
            graph_id: hierGraphId,
            training_config: {
              epochs: payload.hierfl.trainingConfig.epochs,
              lr: payload.hierfl.trainingConfig.lr,
              model_complexity: payload.hierfl.trainingConfig.modelComplexity,
              batch_size: payload.hierfl.trainingConfig.batchSize,
            },
            simulation_settings: {
              run_time_limit: payload.hierfl.simulationSettings.runTimeLimit,
              eval_interval: payload.hierfl.simulationSettings.evalInterval,
              gpu_budget: payload.hierfl.simulationSettings.gpuBudget,
              dataset: payload.hierfl.simulationSettings.dataset,
              seed_set: payload.hierfl.simulationSettings.seedSet,
              repetitions: payload.hierfl.simulationSettings.repetitions,
              output_filename: payload.hierfl.simulationSettings.outputFilename || null,
              evaluate_model: payload.hierfl.simulationSettings.evaluateModel,
            },
          },
          spyker: {
            graph_id: spykerGraphId,
            training_config: {
              epochs: payload.spyker.trainingConfig.epochs,
              lr: payload.spyker.trainingConfig.lr,
              model_complexity: payload.spyker.trainingConfig.modelComplexity,
              batch_size: payload.spyker.trainingConfig.batchSize,
            },
            simulation_settings: {
              run_time_limit: payload.spyker.simulationSettings.runTimeLimit,
              eval_interval: payload.spyker.simulationSettings.evalInterval,
              gpu_budget: payload.spyker.simulationSettings.gpuBudget,
              dataset: payload.spyker.simulationSettings.dataset,
              idle_token_delay: payload.spyker.simulationSettings.idleTokenDelay,
              seed_set: payload.spyker.simulationSettings.seedSet,
              repetitions: payload.spyker.simulationSettings.repetitions,
              output_filename: payload.spyker.simulationSettings.outputFilename || null,
              evaluate_model: payload.spyker.simulationSettings.evaluateModel,
            },
            spyker_config: {
              decay_beta: payload.spyker.spykerConfig.decayBeta,
              min_learning_rate: payload.spyker.spykerConfig.minLearningRate,
              h_inter: payload.spyker.spykerConfig.hInter,
              h_intra: payload.spyker.spykerConfig.hIntra,
              sigmoid_phi: payload.spyker.spykerConfig.sigmoidPhi,
              server_learning_rate: payload.spyker.spykerConfig.serverLearningRate,
              tcp_rto_delay: payload.spyker.spykerConfig.tcpRtoDelay,
            },
          },
        });
        await this.waitForCombinedRunCompletion(queuedRun.run_id, jobId);
      } catch {
        this.showErrorToast('Failed to start combined simulation.');
        this.frameworkJobs.markFailed(jobId);
      } finally {
        this.simulationRunning.set(false);
      }
    } else {
      this.simulationRunning.set(true);
      try {
        await runFor(payload.mode);
      } finally {
        this.simulationRunning.set(false);
      }
    }
  }

  private showSuccessToast(message: string) {
    this.messageService.add({
      severity: 'success',
      summary: 'Simulation completed',
      detail: message,
    });
  }

  private showInfoToast(message: string) {
    this.messageService.add({
      severity: 'info',
      summary: 'Simulation running',
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

  private showValidationErrors(architecture: Architecture, errors: string[]): void {
    const maxErrors = 5;
    const shown = errors.slice(0, maxErrors).map((err) => `- ${err}`).join('\n');
    const remaining = errors.length > maxErrors ? `\n...and ${errors.length - maxErrors} more` : '';
    this.messageService.add({
      severity: 'error',
      summary: `${architecture} validation failed`,
      detail: `${shown}${remaining}`,
      life: 8000,
    });
  }

  private formatSimulationResult(
    architecture: Architecture,
    result: {
      repetitions?: number | null;
      output_filename?: string | null;
      evaluation?: { accuracy: number; avg_loss: number } | null;
      evaluation_summary?: {
        evaluated_repetitions: number;
        mean_accuracy: number;
        variance_accuracy: number;
        mean_avg_loss: number;
        variance_avg_loss: number;
      } | null;
    }
  ): string {
    const parts: string[] = [];
    const repetitions = result.repetitions ?? 1;
    if (repetitions > 1) {
      parts.push(`${repetitions} repetitions completed`);
    } else if (result.output_filename) {
      parts.push(`Saved to ${result.output_filename}`);
    } else {
      parts.push('Completed');
    }
    if (result.evaluation_summary) {
      const meanAccuracyPct = (result.evaluation_summary.mean_accuracy * 100).toFixed(2);
      const varianceAccuracy = result.evaluation_summary.variance_accuracy.toFixed(6);
      const meanLoss = result.evaluation_summary.mean_avg_loss.toFixed(4);
      const varianceLoss = result.evaluation_summary.variance_avg_loss.toFixed(6);
      parts.push(`Mean accuracy ${meanAccuracyPct}%`);
      parts.push(`Accuracy variance ${varianceAccuracy}`);
      parts.push(`Mean loss ${meanLoss}`);
      parts.push(`Loss variance ${varianceLoss}`);
    } else if (result.evaluation) {
      const accuracyPct = (result.evaluation.accuracy * 100).toFixed(2);
      const loss = result.evaluation.avg_loss.toFixed(4);
      parts.push(`Accuracy ${accuracyPct}%`);
      parts.push(`Loss ${loss}`);
    }
    return `${architecture}: ${parts.join(', ')}`;
    return `${architecture}: ${parts.join(' • ')}`;
  }

  private async waitForRunCompletion(
    runId: string,
    architecture: Architecture,
    jobId: string
  ): Promise<void> {
    const run = await this.pollRunUntilFinished(runId, architecture, jobId);
    if (run) {
      this.showSuccessToast(this.formatSimulationResult(architecture, run));
    }
  }

  private async waitForCombinedRunCompletion(runId: string, jobId: string): Promise<void> {
    const run = await this.pollRunUntilFinished(runId, 'combined', jobId);
    const results = run?.results_by_architecture ?? {};
    for (const architecture of ['hierfl', 'spyker'] as const) {
      const result = results[architecture];
      if (result) {
        this.showSuccessToast(this.formatSimulationResult(architecture, result));
      }
    }
  }

  /** Polls a run, mirroring its state into the job list. Resolves with the run once it completed. */
  private async pollRunUntilFinished(
    runId: string,
    label: string,
    jobId: string
  ): Promise<SimulationRunResponse | null> {
    let lastStatus: SimulationRunResponse['status'] | null = null;
    let failedPolls = 0;
    for (;;) {
      let run: SimulationRunResponse;
      try {
        run = await this.graphApi.getRunStatus(runId);
        failedPolls = 0;
      } catch {
        failedPolls += 1;
        if (failedPolls >= MAX_FAILED_STATUS_POLLS) {
          this.frameworkJobs.markFailed(jobId);
          this.showErrorToast(`Lost track of the ${label} run ${runId}. Check the dashboard for its status.`);
          return null;
        }
        await this.sleep(RUN_STATUS_POLL_MS);
        continue;
      }
      if (run.status !== lastStatus) {
        console.info(`[simulation] run status changed: runId=${runId} run=${label} status=${run.status}`);
        lastStatus = run.status;
      }
      if (run.status === 'running') {
        this.frameworkJobs.markRunning(jobId);
      }
      if (run.status === 'completed') {
        this.frameworkJobs.markCompleted(jobId);
        return run;
      }
      if (run.status === 'failed') {
        this.frameworkJobs.markFailed(jobId);
        const detail = run.error ? ` (${run.error})` : '';
        this.showErrorToast(`${label} simulation failed${detail}`);
        return null;
      }
      await this.sleep(RUN_STATUS_POLL_MS);
    }
  }

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  private haveMatchingSeedSet(first: number[], second: number[]): boolean {
    return first.length === second.length && first.every((value, index) => value === second[index]);
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
