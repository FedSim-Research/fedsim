import { Component, HostListener, Inject, Output, EventEmitter, ViewChild, ElementRef, Input, OnInit, OnDestroy } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StartPopup } from '../start.popup/start.popup';
import { ResetButton } from '../reset.button/reset.button';
import { ViewGraphsDialog } from '../view-graphs.component/view-graphs.component';
import { HelpDialog } from '../help-dialog/help-dialog.component';
import { SidebarDashboardPanelComponent } from '../sidebar-dashboard-panel/sidebar-dashboard-panel.component';
import { ToastModule } from 'primeng/toast';
import { MessageService } from 'primeng/api';
import { Shortcuts } from '../../directives/shortcuts';
import { GraphApiService, PresetResponse } from '../../services/graph-api.service';

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

type BlueprintItem<T> = {
  id: number;
  name: string;
  config: T;
};

type SavePresetTarget = {
  kind: 'superserver' | 'server' | 'client';
  index: number;
  name: string;
};

type WorkspaceView = 'editor' | 'dashboard';

const DEFAULT_SUPER_SERVER_CONFIG: SuperServerConfig = {
  name: 'Super Server',
  computeFactor: 2.0,
  performanceSigma: 0.0,
  uploadMbps: 20,
  downloadMbps: 100,
};

const DEFAULT_SERVER_CONFIG: ServerConfig = {
  name: 'Server Node',
  environment: 'Spyker',
  computeFactor: 2.0,
  performanceSigma: 0.0,
  uploadMbps: 20,
  downloadMbps: 100,
};

const DEFAULT_CLIENT_CONFIG: ClientConfig = {
  count: 50,
  type: 'mobile',
  computeFactor: 0.8,
  performanceSigma: 0.0,
  uploadMbps: 2,
  downloadMbps: 10,
};

@Component({
  selector: 'app-sidebar',
  standalone: true,
  templateUrl: './sidebar.component.html',
  styleUrls: ['./sidebar.component.css'],
  imports: [FormsModule, CommonModule, StartPopup, ResetButton, ViewGraphsDialog, HelpDialog, SidebarDashboardPanelComponent, ToastModule],
})
export class SidebarComponent implements OnInit, OnDestroy {
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
  public showConfirmSavePresetPopup = false;
  public deletePresetTarget: { kind: 'superserver' | 'server' | 'client'; index: number; name: string } | null = null;
  public savePresetTarget: SavePresetTarget | null = null;
  @ViewChild('supDetails') private supDetails?: ElementRef<HTMLDetailsElement>;

  @Input() shortcuts?: Shortcuts;
  @Input() activeView: WorkspaceView = 'editor';
  @Output() resetGraph = new EventEmitter<void>();
  @Output() modeChange = new EventEmitter<'spyker' | 'hierfl'>();
  @Output() viewChange = new EventEmitter<WorkspaceView>();
  @Output() sidebarOpenChange = new EventEmitter<boolean>();
  @Output() graphSelected = new EventEmitter<{ graphId: number; architecture: 'spyker' | 'hierfl' }>();
  @Output() simulationRequested = new EventEmitter<{
    mode: 'spyker' | 'hierfl' | 'both';
    hierfl: {
      trainingConfig: { epochs: number; lr: number; modelComplexity: number };
      simulationSettings: { runTimeLimit: number; evalInterval: number; gpuBudget: number; seed: number; outputFilename: string; evaluateModel: boolean };
    };
    spyker: {
      trainingConfig: { epochs: number; lr: number; modelComplexity: number };
      simulationSettings: { runTimeLimit: number; evalInterval: number; gpuBudget: number; seed: number; idleTokenDelay: number; outputFilename: string; evaluateModel: boolean };
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
  }>();

  public selectedArchitectures = {
    spyker: false,
    hierfl: true,
  };
  public architectureMode: 'spyker' | 'hierfl' = 'hierfl';
  public architectureMenuOpen = false;

  public configDraft: {
    superserver: SuperServerConfig;
    server: ServerConfig;
    client: ClientConfig;
  } = {
    superserver: { ...DEFAULT_SUPER_SERVER_CONFIG },
    server: { ...DEFAULT_SERVER_CONFIG },
    client: { ...DEFAULT_CLIENT_CONFIG }
  };

  public superServerBlueprints: BlueprintItem<SuperServerConfig>[] = [];
  public serverBlueprints: BlueprintItem<ServerConfig>[] = [];
  public clientBlueprints: BlueprintItem<ClientConfig>[] = [];

  public selectedSuperServerBlueprintIndex: number | null = null;
  public selectedServerBlueprintIndex: number | null = null;
  public selectedClientBlueprintIndex: number | null = null;

  private readonly nodeForwardListener = (event: Event): void => {
    const customEvent = event as CustomEvent<{ kind: 'superserver' | 'server' | 'client'; config: Record<string, unknown> }>;
    const detail = customEvent.detail;
    if (!detail) {
      return;
    }

    if (detail.kind === 'superserver') {
      this.configDraft.superserver = this.toSuperServerConfig(detail.config);
    } else if (detail.kind === 'server') {
      this.configDraft.server = this.toServerConfig(detail.config);
    } else if (detail.kind === 'client') {
      this.configDraft.client = this.toClientConfig(detail.config);
    }

    this.openSidebar();
  };

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
    private graphApi: GraphApiService
  ) {}

  public async ngOnInit(): Promise<void> {
    this.architectureMode = this.currentArchitecture();
    this.sidebarOpenChange.emit(this.isOpen);
    window.addEventListener('node-forward', this.nodeForwardListener as EventListener);
    await this.ensureGraphForMode(this.currentArchitecture());
    await this.loadPresetsForCurrentArchitecture();
  }

  public ngOnDestroy(): void {
    window.removeEventListener('node-forward', this.nodeForwardListener as EventListener);
  }

  private showErrorToast(message: string) {
    this.messageService.add({
      severity: 'error',
      summary: 'Error',
      detail: message,
    });
  }

  private showSuccessToast(message: string): void {
    this.messageService.add({
      severity: 'success',
      summary: 'Success',
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
    this.architectureMode = this.currentArchitecture();
    this.modeChange.emit(this.selectedArchitectures.spyker ? 'spyker' : 'hierfl');
    if (this.selectedArchitectures.spyker) {
      this.closeSuperServerDisclosure();
    }
    await this.ensureGraphForMode(this.currentArchitecture());
    await this.loadPresetsForCurrentArchitecture();
  }

  public async setArchitecture(isSpyker: boolean): Promise<void> {
    this.selectedArchitectures.spyker = isSpyker;
    this.selectedArchitectures.hierfl = !isSpyker;
    this.architectureMode = this.currentArchitecture();
    this.modeChange.emit(isSpyker ? 'spyker' : 'hierfl');
    if (isSpyker) {
      this.closeSuperServerDisclosure();
    }
    await this.ensureGraphForMode(this.currentArchitecture());
    await this.loadPresetsForCurrentArchitecture();
  }

  public setView(view: WorkspaceView): void {
    if (this.activeView === view) {
      return;
    }
    this.viewChange.emit(view);
  }

  public async onArchitectureModeChange(mode: 'spyker' | 'hierfl'): Promise<void> {
    await this.setArchitecture(mode === 'spyker');
  }

  public toggleArchitectureMenu(event?: Event): void {
    event?.stopPropagation();
    this.architectureMenuOpen = !this.architectureMenuOpen;
  }

  public closeArchitectureMenu(): void {
    this.architectureMenuOpen = false;
  }

  public architectureLabel(): string {
    return this.architectureMode === 'spyker' ? 'Spyker' : 'Hierarchical';
  }

  public async selectArchitectureMode(mode: 'spyker' | 'hierfl', event?: Event): Promise<void> {
    event?.stopPropagation();
    this.architectureMenuOpen = false;
    if (mode === this.architectureMode) {
      return;
    }
    this.architectureMode = mode;
    await this.onArchitectureModeChange(mode);
  }

  @HostListener('document:click', ['$event'])
  public onDocumentClick(event: Event): void {
    const target = event.target as HTMLElement | null;
    if (!target?.closest('.architecture-select')) {
      this.architectureMenuOpen = false;
    }
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

  private currentArchitecture(): 'spyker' | 'hierfl' {
    return this.selectedArchitectures.spyker ? 'spyker' : 'hierfl';
  }

  private toSuperServerConfig(config: Record<string, unknown>): SuperServerConfig {
    return { ...DEFAULT_SUPER_SERVER_CONFIG, ...(config as Partial<SuperServerConfig>) };
  }

  private toServerConfig(config: Record<string, unknown>): ServerConfig {
    return { ...DEFAULT_SERVER_CONFIG, ...(config as Partial<ServerConfig>) };
  }

  private toClientConfig(config: Record<string, unknown>): ClientConfig {
    return { ...DEFAULT_CLIENT_CONFIG, ...(config as Partial<ClientConfig>) };
  }

  private mapSuperServerPreset(preset: PresetResponse): BlueprintItem<SuperServerConfig> {
    return { id: preset.preset_id, name: preset.name, config: this.toSuperServerConfig(preset.config) };
  }

  private mapServerPreset(preset: PresetResponse): BlueprintItem<ServerConfig> {
    return { id: preset.preset_id, name: preset.name, config: this.toServerConfig(preset.config) };
  }

  private mapClientPreset(preset: PresetResponse): BlueprintItem<ClientConfig> {
    return { id: preset.preset_id, name: preset.name, config: this.toClientConfig(preset.config) };
  }

  private async loadPresetsForCurrentArchitecture(): Promise<void> {
    const architecture = this.currentArchitecture();
    try {
      const [superPresets, serverPresets, clientPresets] = await Promise.all([
        this.graphApi.listPresets(architecture, 'SuperServerNode'),
        this.graphApi.listPresets(architecture, 'ServerNode'),
        this.graphApi.listPresets(architecture, 'ClientNode'),
      ]);

      this.superServerBlueprints = superPresets.map((preset) => this.mapSuperServerPreset(preset));
      this.serverBlueprints = serverPresets.map((preset) => this.mapServerPreset(preset));
      this.clientBlueprints = clientPresets.map((preset) => this.mapClientPreset(preset));
      this.selectedSuperServerBlueprintIndex = null;
      this.selectedServerBlueprintIndex = null;
      this.selectedClientBlueprintIndex = null;
    } catch {
      this.showErrorToast('Could not load presets from backend.');
    }
  }

  public toggleSidebar(): void {
    this.setSidebarOpen(!this.isOpen);
  }

  public openSidebar(): void {
    this.setSidebarOpen(true);
  }

  public closeSidebar(): void {
    this.setSidebarOpen(false);
  }

  private setSidebarOpen(next: boolean): void {
    if (this.isOpen === next) {
      return;
    }
    this.isOpen = next;
    this.sidebarOpenChange.emit(this.isOpen);
  }

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

  public async saveSuperServerBlueprint(): Promise<void> {
    const name = this.superServerBlueprintDraft.presetName.trim()
      || `Super Server Preset ${this.superServerBlueprints.length + 1}`;
    const selected = this.selectedSuperServerBlueprintIndex;
    try {
      if (selected !== null && this.superServerBlueprints[selected]) {
        const existing = this.superServerBlueprints[selected];
        const updated = await this.graphApi.updatePreset(existing.id, {
          name,
          config: { ...this.superServerBlueprintDraft.config },
        });
        this.superServerBlueprints[selected] = this.mapSuperServerPreset(updated);
        this.applySuperServerBlueprint(this.superServerBlueprints[selected], selected);
        this.showSuccessToast(`Updated preset "${name}".`);
        return;
      }
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'SuperServerNode',
        name,
        config: { ...this.superServerBlueprintDraft.config },
      });
      this.superServerBlueprints.push(this.mapSuperServerPreset(created));
      this.selectedSuperServerBlueprintIndex = this.superServerBlueprints.length - 1;
      this.applySuperServerBlueprint(this.superServerBlueprints[this.selectedSuperServerBlueprintIndex], this.selectedSuperServerBlueprintIndex);
      this.showSuccessToast(`Saved preset "${name}".`);
    } catch {
      this.showErrorToast('Could not save super server preset.');
    }
  }

  public async createNewSuperServerPreset(): Promise<void> {
    const name = `Super Server Preset ${this.superServerBlueprints.length + 1}`;
    try {
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'SuperServerNode',
        name,
        config: { ...DEFAULT_SUPER_SERVER_CONFIG },
      });
      this.superServerBlueprints.push(this.mapSuperServerPreset(created));
      const index = this.superServerBlueprints.length - 1;
      this.applySuperServerBlueprint(this.superServerBlueprints[index], index);
      this.showSuccessToast(`Created preset "${name}".`);
    } catch {
      this.showErrorToast('Could not create super server preset.');
    }
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

  public async saveServerBlueprint(): Promise<void> {
    const name = this.serverBlueprintDraft.presetName.trim()
      || `Server Node Preset ${this.serverBlueprints.length + 1}`;
    const selected = this.selectedServerBlueprintIndex;
    try {
      if (selected !== null && this.serverBlueprints[selected]) {
        const existing = this.serverBlueprints[selected];
        const updated = await this.graphApi.updatePreset(existing.id, {
          name,
          config: { ...this.serverBlueprintDraft.config },
        });
        this.serverBlueprints[selected] = this.mapServerPreset(updated);
        this.applyServerBlueprint(this.serverBlueprints[selected], selected);
        this.showSuccessToast(`Updated preset "${name}".`);
        return;
      }
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'ServerNode',
        name,
        config: { ...this.serverBlueprintDraft.config },
      });
      this.serverBlueprints.push(this.mapServerPreset(created));
      this.selectedServerBlueprintIndex = this.serverBlueprints.length - 1;
      this.applyServerBlueprint(this.serverBlueprints[this.selectedServerBlueprintIndex], this.selectedServerBlueprintIndex);
      this.showSuccessToast(`Saved preset "${name}".`);
    } catch {
      this.showErrorToast('Could not save server preset.');
    }
  }

  public async createNewServerPreset(): Promise<void> {
    const name = `Server Node Preset ${this.serverBlueprints.length + 1}`;
    try {
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'ServerNode',
        name,
        config: { ...DEFAULT_SERVER_CONFIG },
      });
      this.serverBlueprints.push(this.mapServerPreset(created));
      const index = this.serverBlueprints.length - 1;
      this.applyServerBlueprint(this.serverBlueprints[index], index);
      this.showSuccessToast(`Created preset "${name}".`);
    } catch {
      this.showErrorToast('Could not create server preset.');
    }
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

  public async saveClientBlueprint(): Promise<void> {
    const name = this.clientBlueprintDraft.presetName.trim()
      || `Client Node Preset ${this.clientBlueprints.length + 1}`;
    const selected = this.selectedClientBlueprintIndex;
    try {
      if (selected !== null && this.clientBlueprints[selected]) {
        const existing = this.clientBlueprints[selected];
        const updated = await this.graphApi.updatePreset(existing.id, {
          name,
          config: { ...this.clientBlueprintDraft.config },
        });
        this.clientBlueprints[selected] = this.mapClientPreset(updated);
        this.applyClientBlueprint(this.clientBlueprints[selected], selected);
        this.showSuccessToast(`Updated preset "${name}".`);
        return;
      }
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'ClientNode',
        name,
        config: { ...this.clientBlueprintDraft.config },
      });
      this.clientBlueprints.push(this.mapClientPreset(created));
      this.selectedClientBlueprintIndex = this.clientBlueprints.length - 1;
      this.applyClientBlueprint(this.clientBlueprints[this.selectedClientBlueprintIndex], this.selectedClientBlueprintIndex);
      this.showSuccessToast(`Saved preset "${name}".`);
    } catch {
      this.showErrorToast('Could not save client preset.');
    }
  }

  public async createNewClientPreset(): Promise<void> {
    const name = `Client Node Preset ${this.clientBlueprints.length + 1}`;
    try {
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'ClientNode',
        name,
        config: { ...DEFAULT_CLIENT_CONFIG },
      });
      this.clientBlueprints.push(this.mapClientPreset(created));
      const index = this.clientBlueprints.length - 1;
      this.applyClientBlueprint(this.clientBlueprints[index], index);
      this.showSuccessToast(`Created preset "${name}".`);
    } catch {
      this.showErrorToast('Could not create client preset.');
    }
  }

  public async saveCurrentSuperServerPreset(): Promise<void> {
    const selected = this.selectedSuperServerBlueprintIndex;
    if (selected !== null && this.superServerBlueprints[selected]) {
      this.requestConfirmSavePreset('superserver', selected, this.superServerBlueprints[selected].name);
      return;
    }
    try {
      const name = this.configDraft.superserver.name?.trim() || `Super Server Preset ${this.superServerBlueprints.length + 1}`;
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'SuperServerNode',
        name,
        config: { ...this.configDraft.superserver },
      });
      this.superServerBlueprints.push(this.mapSuperServerPreset(created));
      this.selectedSuperServerBlueprintIndex = this.superServerBlueprints.length - 1;
      this.showSuccessToast(`Saved preset "${name}".`);
    } catch {
      this.showErrorToast('Could not save super server preset.');
    }
  }

  public async saveCurrentServerPreset(): Promise<void> {
    const selected = this.selectedServerBlueprintIndex;
    if (selected !== null && this.serverBlueprints[selected]) {
      this.requestConfirmSavePreset('server', selected, this.serverBlueprints[selected].name);
      return;
    }
    try {
      const name = this.configDraft.server.name?.trim() || `Server Node Preset ${this.serverBlueprints.length + 1}`;
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'ServerNode',
        name,
        config: { ...this.configDraft.server },
      });
      this.serverBlueprints.push(this.mapServerPreset(created));
      this.selectedServerBlueprintIndex = this.serverBlueprints.length - 1;
      this.showSuccessToast(`Saved preset "${name}".`);
    } catch {
      this.showErrorToast('Could not save server preset.');
    }
  }

  public async saveCurrentClientPreset(): Promise<void> {
    const selected = this.selectedClientBlueprintIndex;
    if (selected !== null && this.clientBlueprints[selected]) {
      this.requestConfirmSavePreset('client', selected, this.clientBlueprints[selected].name);
      return;
    }
    try {
      const fallback = `Client Node Preset ${this.clientBlueprints.length + 1}`;
      const name = `Client ${this.configDraft.client.type} x${this.configDraft.client.count}`.trim() || fallback;
      const created = await this.graphApi.createPreset({
        architecture: this.currentArchitecture(),
        node_type: 'ClientNode',
        name,
        config: { ...this.configDraft.client },
      });
      this.clientBlueprints.push(this.mapClientPreset(created));
      this.selectedClientBlueprintIndex = this.clientBlueprints.length - 1;
      this.showSuccessToast(`Saved preset "${name}".`);
    } catch {
      this.showErrorToast('Could not save client preset.');
    }
  }

  public selectSuperServerBlueprint(index: number): void {
    const item = this.superServerBlueprints[index];
    if (!item) {
      return;
    }
    this.applySuperServerBlueprint(item, index);
  }

  public applySuperServerBlueprint(item: BlueprintItem<SuperServerConfig>, index: number): void {
    this.selectedSuperServerBlueprintIndex = index;
    this.superServerBlueprintDraft = {
      presetName: item.name,
      config: { ...item.config },
    };
    this.configDraft.superserver = { ...item.config };
  }

  public selectServerBlueprint(index: number): void {
    const item = this.serverBlueprints[index];
    if (!item) {
      return;
    }
    this.applyServerBlueprint(item, index);
  }

  public applyServerBlueprint(item: BlueprintItem<ServerConfig>, index: number): void {
    this.selectedServerBlueprintIndex = index;
    this.serverBlueprintDraft = {
      presetName: item.name,
      config: { ...item.config },
    };
    this.configDraft.server = { ...item.config };
  }

  public selectClientBlueprint(index: number): void {
    const item = this.clientBlueprints[index];
    if (!item) {
      return;
    }
    this.applyClientBlueprint(item, index);
  }

  public applyClientBlueprint(item: BlueprintItem<ClientConfig>, index: number): void {
    this.selectedClientBlueprintIndex = index;
    this.clientBlueprintDraft = {
      presetName: item.name,
      config: { ...item.config },
    };
    this.configDraft.client = { ...item.config };
  }

  public selectedSuperServerPresetName(): string {
    if (this.selectedSuperServerBlueprintIndex === null) {
      return 'None';
    }
    return this.superServerBlueprints[this.selectedSuperServerBlueprintIndex]?.name ?? 'None';
  }

  public selectedServerPresetName(): string {
    if (this.selectedServerBlueprintIndex === null) {
      return 'None';
    }
    return this.serverBlueprints[this.selectedServerBlueprintIndex]?.name ?? 'None';
  }

  public selectedClientPresetName(): string {
    if (this.selectedClientBlueprintIndex === null) {
      return 'None';
    }
    return this.clientBlueprints[this.selectedClientBlueprintIndex]?.name ?? 'None';
  }

  public async deleteSuperServerBlueprint(index: number): Promise<void> {
    const target = this.superServerBlueprints[index];
    if (!target) {
      return;
    }
    await this.graphApi.deletePreset(target.id);
    this.superServerBlueprints.splice(index, 1);
    if (this.selectedSuperServerBlueprintIndex === index) {
      this.selectedSuperServerBlueprintIndex = null;
    } else if (this.selectedSuperServerBlueprintIndex !== null && this.selectedSuperServerBlueprintIndex > index) {
      this.selectedSuperServerBlueprintIndex -= 1;
    }
  }

  public async deleteServerBlueprint(index: number): Promise<void> {
    const target = this.serverBlueprints[index];
    if (!target) {
      return;
    }
    await this.graphApi.deletePreset(target.id);
    this.serverBlueprints.splice(index, 1);
    if (this.selectedServerBlueprintIndex === index) {
      this.selectedServerBlueprintIndex = null;
    } else if (this.selectedServerBlueprintIndex !== null && this.selectedServerBlueprintIndex > index) {
      this.selectedServerBlueprintIndex -= 1;
    }
  }

  public async deleteClientBlueprint(index: number): Promise<void> {
    const target = this.clientBlueprints[index];
    if (!target) {
      return;
    }
    await this.graphApi.deletePreset(target.id);
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

  public requestConfirmSavePreset(
    kind: 'superserver' | 'server' | 'client',
    index: number,
    name: string
  ): void {
    this.savePresetTarget = { kind, index, name };
    this.showConfirmSavePresetPopup = true;
  }

  public closeConfirmSavePresetPopup(): void {
    this.showConfirmSavePresetPopup = false;
    this.savePresetTarget = null;
  }

  public async confirmUpdateSelectedPreset(): Promise<void> {
    if (!this.savePresetTarget) {
      return;
    }
    const { kind, index } = this.savePresetTarget;
    try {
      if (kind === 'superserver') {
        const existing = this.superServerBlueprints[index];
        if (!existing) {
          this.closeConfirmSavePresetPopup();
          return;
        }
        const updated = await this.graphApi.updatePreset(existing.id, {
          config: { ...this.configDraft.superserver },
        });
        this.superServerBlueprints[index] = this.mapSuperServerPreset(updated);
        this.selectedSuperServerBlueprintIndex = index;
        this.showSuccessToast(`Updated preset "${this.superServerBlueprints[index].name}".`);
      } else if (kind === 'server') {
        const existing = this.serverBlueprints[index];
        if (!existing) {
          this.closeConfirmSavePresetPopup();
          return;
        }
        const updated = await this.graphApi.updatePreset(existing.id, {
          config: { ...this.configDraft.server },
        });
        this.serverBlueprints[index] = this.mapServerPreset(updated);
        this.selectedServerBlueprintIndex = index;
        this.showSuccessToast(`Updated preset "${this.serverBlueprints[index].name}".`);
      } else {
        const existing = this.clientBlueprints[index];
        if (!existing) {
          this.closeConfirmSavePresetPopup();
          return;
        }
        const updated = await this.graphApi.updatePreset(existing.id, {
          config: { ...this.configDraft.client },
        });
        this.clientBlueprints[index] = this.mapClientPreset(updated);
        this.selectedClientBlueprintIndex = index;
        this.showSuccessToast(`Updated preset "${this.clientBlueprints[index].name}".`);
      }
      this.closeConfirmSavePresetPopup();
    } catch {
      this.showErrorToast('Could not update preset.');
    }
  }

  public async confirmCreateNewPresetFromSidebar(): Promise<void> {
    if (!this.savePresetTarget) {
      return;
    }
    const kind = this.savePresetTarget.kind;
    try {
      if (kind === 'superserver') {
        const name = this.configDraft.superserver.name?.trim() || `Super Server Preset ${this.superServerBlueprints.length + 1}`;
        const created = await this.graphApi.createPreset({
          architecture: this.currentArchitecture(),
          node_type: 'SuperServerNode',
          name,
          config: { ...this.configDraft.superserver },
        });
        this.superServerBlueprints.push(this.mapSuperServerPreset(created));
        this.selectedSuperServerBlueprintIndex = this.superServerBlueprints.length - 1;
      } else if (kind === 'server') {
        const name = this.configDraft.server.name?.trim() || `Server Node Preset ${this.serverBlueprints.length + 1}`;
        const created = await this.graphApi.createPreset({
          architecture: this.currentArchitecture(),
          node_type: 'ServerNode',
          name,
          config: { ...this.configDraft.server },
        });
        this.serverBlueprints.push(this.mapServerPreset(created));
        this.selectedServerBlueprintIndex = this.serverBlueprints.length - 1;
      } else {
        const fallback = `Client Node Preset ${this.clientBlueprints.length + 1}`;
        const name = `Client ${this.configDraft.client.type} x${this.configDraft.client.count}`.trim() || fallback;
        const created = await this.graphApi.createPreset({
          architecture: this.currentArchitecture(),
          node_type: 'ClientNode',
          name,
          config: { ...this.configDraft.client },
        });
        this.clientBlueprints.push(this.mapClientPreset(created));
        this.selectedClientBlueprintIndex = this.clientBlueprints.length - 1;
      }
      this.closeConfirmSavePresetPopup();
      this.showSuccessToast('Created a new preset.');
    } catch {
      this.showErrorToast('Could not create new preset.');
    }
  }

  public async confirmDeletePreset(): Promise<void> {
    if (!this.deletePresetTarget) {
      return;
    }

    const { kind, index } = this.deletePresetTarget;
    try {
      if (kind === 'superserver') {
        await this.deleteSuperServerBlueprint(index);
      } else if (kind === 'server') {
        await this.deleteServerBlueprint(index);
      } else {
        await this.deleteClientBlueprint(index);
      }
      this.closeDeletePresetPopup();
      this.showSuccessToast('Preset deleted.');
    } catch {
      this.showErrorToast('Could not delete preset.');
    }
  }

  public loadSuperServerPreset(): void {
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
    this.applySuperServerBlueprint(item, this.selectedSuperServerBlueprintIndex);
    this.closeSuperServerBlueprintPopup();
    this.showSuccessToast(`"${item.name}" is now selected. Drag a Super Server node to place it.`);
  }

  public loadServerPreset(): void {
    if (this.selectedServerBlueprintIndex === null) {
      this.showErrorToast('Select a server node preset first.');
      return;
    }
    const item = this.serverBlueprints[this.selectedServerBlueprintIndex];
    if (!item) {
      this.showErrorToast('Preset not found.');
      return;
    }
    this.applyServerBlueprint(item, this.selectedServerBlueprintIndex);
    this.closeServerBlueprintPopup();
    this.showSuccessToast(`"${item.name}" is now selected. Drag a Server node to place it.`);
  }

  public loadClientPreset(): void {
    if (this.selectedClientBlueprintIndex === null) {
      this.showErrorToast('Select a client node preset first.');
      return;
    }
    const item = this.clientBlueprints[this.selectedClientBlueprintIndex];
    if (!item) {
      this.showErrorToast('Preset not found.');
      return;
    }
    this.applyClientBlueprint(item, this.selectedClientBlueprintIndex);
    this.closeClientBlueprintPopup();
    this.showSuccessToast(`"${item.name}" is now selected. Drag a Client node to place it.`);
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
  
  public runSimulation(payload: {
    mode: 'spyker' | 'hierfl' | 'both';
    hierfl: {
      trainingConfig: { epochs: number; lr: number; modelComplexity: number };
      simulationSettings: { runTimeLimit: number; evalInterval: number; gpuBudget: number; seed: number; outputFilename: string; evaluateModel: boolean };
    };
    spyker: {
      trainingConfig: { epochs: number; lr: number; modelComplexity: number };
      simulationSettings: { runTimeLimit: number; evalInterval: number; gpuBudget: number; seed: number; idleTokenDelay: number; outputFilename: string; evaluateModel: boolean };
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
  }): void {
    this.simulationRequested.emit(payload);
    this.closeSimulationpopup();
  }

  @HostListener('document:keydown.escape')
  public onEscapePressed(): void {
    if (this.architectureMenuOpen) {
      this.closeArchitectureMenu();
      return;
    }
    if (this.showConfirmSavePresetPopup) {
      this.closeConfirmSavePresetPopup();
      return;
    }
    if (this.showDeletePresetPopup) {
      this.closeDeletePresetPopup();
      return;
    }
    if (this.showClientBlueprintPopup) {
      this.closeClientBlueprintPopup();
      return;
    }
    if (this.showServerBlueprintPopup) {
      this.closeServerBlueprintPopup();
      return;
    }
    if (this.showSuperServerBlueprintPopup) {
      this.closeSuperServerBlueprintPopup();
      return;
    }
    if (this.showResetPopup) {
      this.closeResetPopup();
      return;
    }
    if (this.showViewGraphsDialog) {
      this.closeViewGraphsDialog();
      return;
    }
    if (this.showHelpDialog) {
      this.closeHelpDialog();
      return;
    }
    if (this.showSimulationpopup) {
      this.closeSimulationpopup();
    }
  }
}
