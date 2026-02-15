import { Component, Inject, Output, EventEmitter, ViewChild, ElementRef, Input, OnInit } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { Node } from 'ngx-vflow';
import { StartPopup } from '../start.popup/start.popup';
import { ResetButton } from '../reset.button/reset.button';
import { ViewGraphsDialog } from '../view-graphs.component/view-graphs.component';
import { HelpDialog } from '../help-dialog/help-dialog.component';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { Shortcuts } from '../../directives/shortcuts';
import { GraphApiService } from '../../services/graph-api.service';
import { GraphServiceSpyker } from '../../services/subservices/graph-service-spyker';
import { GraphServiceHierach } from '../../services/subservices/graph-service-hierach';
import { ClientNode } from '../nodes/client-node/client-node';
import { ServerNode } from '../nodes/server-node/server-node';
import { SuperServerNode } from '../nodes/super-server-node/super-server-node';

type SuperServerConfig = {
  name: string;
  computeFactor: number;
  performanceSigma: number;
  uploadMbps: number;
  downloadMbps: number;
};

type ServerConfig = {
  name: string;
  environment: string;
  computeFactor: number;
  performanceSigma: number;
  uploadMbps: number;
  downloadMbps: number;
};

type ClientConfig = {
  count: number;
  type: 'laptop' | 'workstation' | 'mobile';
  computeFactor: number;
  performanceSigma: number;
  uploadMbps: number;
  downloadMbps: number;
};

type BlueprintDraft<T> = {
  presetName: string;
  config: T;
};

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
  imports: [FormsModule, CommonModule, StartPopup, ResetButton, ViewGraphsDialog, HelpDialog, ToastModule],
})
export class SidebarComponent implements OnInit {
  public isOpen = true;
  public isDarkMode = true;
  public showSimulationpopup = false;
  public showResetPopup = false;
  public showViewGraphsDialog = false;
  public showHelpDialog = false;
  public showSuperServerBlueprintPopup = false;
  public showServerBlueprintPopup = false;
  public showClientBlueprintPopup = false;
  public showDeletePresetPopup = false;
  public deletePresetTarget: { kind: 'superserver' | 'server' | 'client'; index: number; name: string } | null = null;
  @ViewChild('supDetails') private supDetails?: ElementRef<HTMLDetailsElement>;

  @Input() shortcuts?: Shortcuts;
  @Output() resetGraph = new EventEmitter<void>();
  @Output() modeChange = new EventEmitter<'spyker' | 'hierfl'>();
  @Output() graphSelected = new EventEmitter<{ graphId: number; architecture: 'spyker' | 'hierfl' }>();
  @Output() simulationRequested = new EventEmitter<{
    mode: 'spyker' | 'hierfl' | 'both';
    trainingConfig: { epochs: number; lr: number };
    simulationSettings: { runTimeLimit: number; outputFilename: string; evaluateModel: boolean };
  }>();

  public selectedArchitectures = {
    spyker: false,
    hierfl: true,
  };

  public simulationSettings = {
    epochs: 1,
    lr: 0.01,
    runTimeLimit: 5000,
    outputFilename: 'final_model_hierfl.pth',
    evaluateModel: false,
  };

  public configDraft: {
    superserver: SuperServerConfig;
    server: ServerConfig;
    client: ClientConfig;
  } = {
    superserver: {
      name: 'Super Server',
      computeFactor: 2.0,
      performanceSigma: 0.0,
      uploadMbps: 20,
      downloadMbps: 100,
    },
    server: {
      name: 'Server Node',
      environment: 'Spyker',
      computeFactor: 2.0,
      performanceSigma: 0.0,
      uploadMbps: 20,
      downloadMbps: 100,
    },
    client: {
      count: 50,
      type: 'mobile',
      computeFactor: 0.8,
      performanceSigma: 0.0,
      uploadMbps: 2,
      downloadMbps: 10,
    }
  };

  public superServerBlueprints: Array<{ name: string; config: SuperServerConfig }> = [];
  public serverBlueprints: Array<{ name: string; config: ServerConfig }> = [];
  public clientBlueprints: Array<{ name: string; config: ClientConfig }> = [];

  public selectedSuperServerBlueprintIndex: number | null = null;
  public selectedServerBlueprintIndex: number | null = null;
  public selectedClientBlueprintIndex: number | null = null;

  public superServerBlueprintDraft: BlueprintDraft<SuperServerConfig> = {
    presetName: '',
    config: { ...this.configDraft.superserver },
  };

  public serverBlueprintDraft: BlueprintDraft<ServerConfig> = {
    presetName: '',
    config: { ...this.configDraft.server },
  };

  public clientBlueprintDraft: BlueprintDraft<ClientConfig> = {
    presetName: '',
    config: { ...this.configDraft.client },
  };

  constructor(
    @Inject(DOCUMENT) private document: Document,
    private messageService: MessageService,
    private graphApi: GraphApiService,
    private graphServiceSpyker: GraphServiceSpyker,
    private graphServiceHierach: GraphServiceHierach
  ) {}

  public async ngOnInit(): Promise<void> {
    await this.ensureGraphForMode(this.selectedArchitectures.spyker ? 'spyker' : 'hierfl');
  }

  private showErrorToast(message: string) {
    this.messageService.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
    });
  }

  public onResetRequested(): void {
    this.showResetPopup = true;
  }

  public closeResetPopup(): void {
    this.showResetPopup = false;
  }

  public confirmResetGraph(): void {
    this.resetGraph.emit();
    this.closeResetPopup();
  }

  @Output() undoRequested = new EventEmitter<void>();
  @Output() redoRequested = new EventEmitter<void>();
  
  public redo(): void {
    this.redoRequested.emit();
  }

  public undo(): void {
    this.undoRequested.emit();
  }

  public async toggleArchitecture(): Promise<void> {
    this.selectedArchitectures.spyker = !this.selectedArchitectures.spyker;
    this.selectedArchitectures.hierfl = !this.selectedArchitectures.spyker;
    this.modeChange.emit(this.selectedArchitectures.spyker ? 'spyker' : 'hierfl');
    if (this.selectedArchitectures.spyker) {
      this.closeSuperServerDisclosure();
    }
    await this.ensureGraphForMode(this.selectedArchitectures.spyker ? 'spyker' : 'hierfl');
  }

  public async setArchitecture(isSpyker: boolean): Promise<void> {
    this.selectedArchitectures.spyker = isSpyker;
    this.selectedArchitectures.hierfl = !isSpyker;
    this.modeChange.emit(isSpyker ? 'spyker' : 'hierfl');
    if (isSpyker) {
      this.closeSuperServerDisclosure();
    }
    await this.ensureGraphForMode(isSpyker ? 'spyker' : 'hierfl');
  }

  private async ensureGraphForMode(mode: 'spyker' | 'hierfl'): Promise<void> {
    try {
      const graphs = await this.graphApi.listGraphs();
      const hasGraph = graphs.some((graph) => graph.architecture === mode);
      if (!hasGraph) {
        this.showViewGraphsDialog = true;
      }
    } catch {
      // Ignore loading errors for auto-open behavior.
    }
  }

  public toggleSidebar(): void { this.isOpen = !this.isOpen; }
  public openSidebar(): void { this.isOpen = true; }
  public closeSidebar(): void { this.isOpen = false; }

  public toggleTheme(): void {
    this.isDarkMode = !this.isDarkMode;
    if (this.isDarkMode) { this.document.body.classList.remove('light-mode'); } 
    else { this.document.body.classList.add('light-mode'); }
  }

  public onDragStart(event: DragEvent, kind: 'SuperServerNode' | 'ServerNode' | 'ClientNode'): void {
    if (kind === 'SuperServerNode') {
      if (this.selectedArchitectures.spyker) {
        event.preventDefault();
        event.stopPropagation();
        this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
        return;
      }
      const allGraphNodes = document.querySelectorAll('.vflow-node');
      const alreadyExists = Array.from(allGraphNodes).some(node => {
        const text = node.textContent?.toLowerCase().replace(/\s+/g, '') ?? '';
        return text.includes('superserver');
      });
      if (alreadyExists) {
        event.preventDefault();
        event.stopPropagation();
        this.showErrorToast('Only one Super Server can exist in the Environment Hierarchical.');
        return;
      }
    }
    const configByKind = {
      SuperServerNode: { ...this.configDraft.superserver },
      ServerNode: { ...this.configDraft.server },
      ClientNode: { ...this.configDraft.client },
    } as const;

    const payload = { type: kind, config: configByKind[kind] };
    if (event.dataTransfer) {
      event.dataTransfer.setData('application/json', JSON.stringify(payload));
      event.dataTransfer.effectAllowed = 'copy';
    }
  }

  public openSimulationpopup(): void { this.showSimulationpopup = true; }
  public closeSimulationpopup(): void { this.showSimulationpopup = false; }
  public openSuperServerBlueprintPopup(): void {
    this.superServerBlueprintDraft = {
      presetName: '',
      config: { ...this.configDraft.superserver },
    };
    this.selectedSuperServerBlueprintIndex = null;
    this.showSuperServerBlueprintPopup = true;
  }

  public closeSuperServerBlueprintPopup(): void {
    this.showSuperServerBlueprintPopup = false;
  }

  public saveSuperServerBlueprint(): void {
    const name = this.superServerBlueprintDraft.presetName.trim()
      || `Super Server Preset ${this.superServerBlueprints.length + 1}`;
    this.superServerBlueprints.push({
      name,
      config: { ...this.superServerBlueprintDraft.config },
    });
  }

  public openServerBlueprintPopup(): void {
    this.serverBlueprintDraft = {
      presetName: '',
      config: { ...this.configDraft.server },
    };
    this.selectedServerBlueprintIndex = null;
    this.showServerBlueprintPopup = true;
  }

  public closeServerBlueprintPopup(): void {
    this.showServerBlueprintPopup = false;
  }

  public saveServerBlueprint(): void {
    const name = this.serverBlueprintDraft.presetName.trim()
      || `Server Node Preset ${this.serverBlueprints.length + 1}`;
    this.serverBlueprints.push({
      name,
      config: { ...this.serverBlueprintDraft.config },
    });
  }

  public openClientBlueprintPopup(): void {
    this.clientBlueprintDraft = {
      presetName: '',
      config: { ...this.configDraft.client },
    };
    this.selectedClientBlueprintIndex = null;
    this.showClientBlueprintPopup = true;
  }

  public closeClientBlueprintPopup(): void {
    this.showClientBlueprintPopup = false;
  }

  public saveClientBlueprint(): void {
    const name = this.clientBlueprintDraft.presetName.trim()
      || `Client Node Preset ${this.clientBlueprints.length + 1}`;
    this.clientBlueprints.push({
      name,
      config: { ...this.clientBlueprintDraft.config },
    });
  }

  public selectSuperServerBlueprint(index: number): void {
    this.selectedSuperServerBlueprintIndex = index;
  }

  public applySuperServerBlueprint(item: { name: string; config: SuperServerConfig }, index: number): void {
    this.selectedSuperServerBlueprintIndex = index;
    this.superServerBlueprintDraft = {
      presetName: item.name,
      config: { ...item.config },
    };
    this.configDraft.superserver = { ...item.config };
  }

  public selectServerBlueprint(index: number): void {
    this.selectedServerBlueprintIndex = index;
  }

  public applyServerBlueprint(item: { name: string; config: ServerConfig }, index: number): void {
    this.selectedServerBlueprintIndex = index;
    this.serverBlueprintDraft = {
      presetName: item.name,
      config: { ...item.config },
    };
    this.configDraft.server = { ...item.config };
  }

  public selectClientBlueprint(index: number): void {
    this.selectedClientBlueprintIndex = index;
  }

  public applyClientBlueprint(item: { name: string; config: ClientConfig }, index: number): void {
    this.selectedClientBlueprintIndex = index;
    this.clientBlueprintDraft = {
      presetName: item.name,
      config: { ...item.config },
    };
    this.configDraft.client = { ...item.config };
  }

  public deleteSuperServerBlueprint(index: number): void {
    this.superServerBlueprints.splice(index, 1);
    if (this.selectedSuperServerBlueprintIndex === index) {
      this.selectedSuperServerBlueprintIndex = null;
    } else if (this.selectedSuperServerBlueprintIndex !== null && this.selectedSuperServerBlueprintIndex > index) {
      this.selectedSuperServerBlueprintIndex -= 1;
    }
  }

  public deleteServerBlueprint(index: number): void {
    this.serverBlueprints.splice(index, 1);
    if (this.selectedServerBlueprintIndex === index) {
      this.selectedServerBlueprintIndex = null;
    } else if (this.selectedServerBlueprintIndex !== null && this.selectedServerBlueprintIndex > index) {
      this.selectedServerBlueprintIndex -= 1;
    }
  }

  public deleteClientBlueprint(index: number): void {
    this.clientBlueprints.splice(index, 1);
    if (this.selectedClientBlueprintIndex === index) {
      this.selectedClientBlueprintIndex = null;
    } else if (this.selectedClientBlueprintIndex !== null && this.selectedClientBlueprintIndex > index) {
      this.selectedClientBlueprintIndex -= 1;
    }
  }

  public requestDeletePreset(kind: 'superserver' | 'server' | 'client', index: number): void {
    const name = kind === 'superserver'
      ? this.superServerBlueprints[index]?.name
      : kind === 'server'
        ? this.serverBlueprints[index]?.name
        : this.clientBlueprints[index]?.name;

    if (!name) {
      return;
    }

    this.deletePresetTarget = { kind, index, name };
    this.showDeletePresetPopup = true;
  }

  public closeDeletePresetPopup(): void {
    this.showDeletePresetPopup = false;
    this.deletePresetTarget = null;
  }

  public confirmDeletePreset(): void {
    if (!this.deletePresetTarget) {
      return;
    }

    const { kind, index } = this.deletePresetTarget;
    if (kind === 'superserver') {
      this.deleteSuperServerBlueprint(index);
    } else if (kind === 'server') {
      this.deleteServerBlueprint(index);
    } else {
      this.deleteClientBlueprint(index);
    }

    this.closeDeletePresetPopup();
  }

  public initializeSuperServerPreset(): void {
    if (this.selectedSuperServerBlueprintIndex === null) {
      this.showErrorToast('Select a super server preset first.');
      return;
    }
    const item = this.superServerBlueprints[this.selectedSuperServerBlueprintIndex];
    if (!item) {
      this.showErrorToast('Preset not found.');
      return;
    }
    if (this.selectedArchitectures.spyker) {
      this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
      return;
    }
    this.createNodeFromPreset('SuperServerNode', item.config);
  }

  public initializeServerPreset(): void {
    if (this.selectedServerBlueprintIndex === null) {
      this.showErrorToast('Select a server node preset first.');
      return;
    }
    const item = this.serverBlueprints[this.selectedServerBlueprintIndex];
    if (!item) {
      this.showErrorToast('Preset not found.');
      return;
    }
    this.createNodeFromPreset('ServerNode', item.config);
  }

  public initializeClientPreset(): void {
    if (this.selectedClientBlueprintIndex === null) {
      this.showErrorToast('Select a client node preset first.');
      return;
    }
    const item = this.clientBlueprints[this.selectedClientBlueprintIndex];
    if (!item) {
      this.showErrorToast('Preset not found.');
      return;
    }
    this.createNodeFromPreset('ClientNode', item.config);
  }

  private createNodeFromPreset(
    kind: 'SuperServerNode' | 'ServerNode' | 'ClientNode',
    config: SuperServerConfig | ServerConfig | ClientConfig
  ): void {
    const nodeType = kind === 'SuperServerNode'
      ? SuperServerNode
      : kind === 'ServerNode'
        ? ServerNode
        : ClientNode;

    const service = this.selectedArchitectures.spyker
      ? this.graphServiceSpyker
      : this.graphServiceHierach;

    const nodes = service.nodes();
    const lastPoint = nodes.length ? nodes[nodes.length - 1].point : null;
    const point = lastPoint
      ? { x: lastPoint.x + 40, y: lastPoint.y + 40 }
      : { x: 160, y: 160 };

    const newNode: Node = {
      id: crypto.randomUUID(),
      point,
      type: nodeType,
      data: {
        type: kind,
        config,
        environment: this.selectedArchitectures.spyker ? 'spyker' : 'hierfl',
        fromJson: false,
        selected: false,
      },
    };

    service.addNode(newNode);
  }
  public onSuperServerSummaryClick(event: Event): void {
    if (this.selectedArchitectures.spyker) {
      event.preventDefault();
      this.closeSuperServerDisclosure();
      this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
    }
  }
  private closeSuperServerDisclosure(): void {
    this.supDetails?.nativeElement.removeAttribute('open');
  }

  public openViewGraphsDialog(): void {
    this.showViewGraphsDialog = true;
  }

  public closeViewGraphsDialog(): void {
    this.showViewGraphsDialog = false;
  }

  public openHelpDialog(): void {
    this.showHelpDialog = true;
  }

  public closeHelpDialog(): void {
    this.showHelpDialog = false;
  }

  public onGraphSelected(event: { graphId: number; architecture: 'spyker' | 'hierfl' }): void {
    this.graphSelected.emit(event);
    this.closeViewGraphsDialog();
  }
  
  public runSimulation(type: 'spyker' | 'hierarchical' | 'both'): void { 
    const normalized = type === 'hierarchical' ? 'hierfl' : type;
    this.simulationRequested.emit({
      mode: normalized,
      trainingConfig: {
        epochs: this.simulationSettings.epochs,
        lr: this.simulationSettings.lr,
      },
      simulationSettings: {
        runTimeLimit: this.simulationSettings.runTimeLimit,
        outputFilename: this.simulationSettings.outputFilename,
        evaluateModel: this.simulationSettings.evaluateModel,
      },
    });
    this.closeSimulationpopup();
  }
}
