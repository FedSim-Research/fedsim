import { Component, HostListener, Output, inject, EventEmitter, ViewChild, ElementRef, Input, OnChanges, OnInit, SimpleChanges } from '@angular/core';
import { CommonModule, DOCUMENT } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { StartPopup } from '../../runs/start-popup/start-popup';
import { ResetButton } from '../../editor/reset-button/reset-button';
import { ViewGraphsDialog } from '../../editor/view-graphs/view-graphs';
import { HelpDialog } from '../help-dialog/help-dialog';
import { SidebarDashboardPanelComponent } from '../../runs/sidebar-dashboard-panel/sidebar-dashboard-panel';
import { MessageService } from 'primeng/api';
import { Shortcuts } from '../../editor/shortcuts.directive';
import { GraphApiService } from '../../api/graph-api.service';
import { PresetLibrary } from './preset-library';
import { NodeEvents, NodeForward } from '../../editor/nodes/node-events.service';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { SimulationRequest } from '../../runs/simulation-request';
import { Architecture, NodeKind } from '../../domain/topology';

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

type PresetKind = 'superserver' | 'server' | 'client';

type PresetConfigs = {
  superserver: SuperServerConfig;
  server: ServerConfig;
  client: ClientConfig;
};

type PresetTarget = {
  kind: PresetKind;
  index: number;
  name: string;
};

const PRESET_KINDS: readonly PresetKind[] = ['superserver', 'server', 'client'];

const PRESET_LABELS: Record<PresetKind, { preset: string; node: string }> = {
  superserver: { preset: 'super server', node: 'Super Server' },
  server: { preset: 'server node', node: 'Server' },
  client: { preset: 'client node', node: 'Client' },
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
  templateUrl: './sidebar.html',
  styleUrls: ['./sidebar.css'],
  imports: [FormsModule, CommonModule, StartPopup, ResetButton, ViewGraphsDialog, HelpDialog, SidebarDashboardPanelComponent],
})
export class SidebarComponent implements OnInit, OnChanges {
  public isOpen = true;
  public isDarkMode = true;
  public showSimulationpopup = false;
  public showResetPopup = false;
  public showViewGraphsDialog = false;
  public showHelpDialog = false;
  public showDeletePresetPopup = false;
  public showConfirmSavePresetPopup = false;
  public deletePresetTarget: PresetTarget | null = null;
  public savePresetTarget: PresetTarget | null = null;
  @ViewChild('supDetails') private supDetails?: ElementRef<HTMLDetailsElement>;

  @Input() shortcuts?: Shortcuts;
  @Input() hierflGraphId: number | null = null;
  @Input() spykerGraphId: number | null = null;
  @Input() activeView: WorkspaceView = 'editor';
  /** Owned by the app shell; the sidebar only requests changes via `modeChange`. */
  @Input() activeMode: Architecture = 'hierfl';
  @Output() resetGraph = new EventEmitter<void>();
  @Output() modeChange = new EventEmitter<Architecture>();
  @Output() viewChange = new EventEmitter<WorkspaceView>();
  @Output() sidebarOpenChange = new EventEmitter<boolean>();
  @Output() graphSelected = new EventEmitter<{ graphId: number; architecture: Architecture }>();
  @Output() graphDeleted = new EventEmitter<{ graphId: number; architecture: Architecture }>();
  @Output() simulationRequested = new EventEmitter<SimulationRequest>();

  public architectureMenuOpen = false;

  private readonly document = inject(DOCUMENT);
  private readonly messageService = inject(MessageService);
  private readonly graphApi = inject(GraphApiService);

  /** Settings the next dragged node of each kind is created with. */
  public configDraft: PresetConfigs = {
    superserver: { ...DEFAULT_SUPER_SERVER_CONFIG },
    server: { ...DEFAULT_SERVER_CONFIG },
    client: { ...DEFAULT_CLIENT_CONFIG }
  };

  public readonly presets: { [K in PresetKind]: PresetLibrary<PresetConfigs[K]> } = {
    superserver: new PresetLibrary(this.graphApi, {
      nodeKind: 'SuperServerNode',
      label: 'Super Server',
      defaults: DEFAULT_SUPER_SERVER_CONFIG,
      nameFor: (config) => config.name,
    }),
    server: new PresetLibrary(this.graphApi, {
      nodeKind: 'ServerNode',
      label: 'Server Node',
      defaults: DEFAULT_SERVER_CONFIG,
      nameFor: (config) => config.name,
    }),
    client: new PresetLibrary(this.graphApi, {
      nodeKind: 'ClientNode',
      label: 'Client Node',
      defaults: DEFAULT_CLIENT_CONFIG,
      nameFor: (config) => `Client ${config.type} x${config.count}`,
    }),
  };

  constructor() {
    inject(NodeEvents)
      .forwarded$.pipe(takeUntilDestroyed())
      .subscribe((forward) => this.takeOverNodeSettings(forward));
  }

  private takeOverNodeSettings({ kind, config }: NodeForward): void {
    if (kind === 'superserver') {
      this.configDraft.superserver = this.toSuperServerConfig(config);
    } else if (kind === 'server') {
      this.configDraft.server = this.toServerConfig(config);
    } else {
      this.configDraft.client = this.toClientConfig(config);
    }
    this.openSidebar();
  }


  public async ngOnInit(): Promise<void> {
    this.sidebarOpenChange.emit(this.isOpen);
    await this.ensureGraphForMode(this.currentArchitecture());
    await this.loadPresetsForCurrentArchitecture();
  }

  public async ngOnChanges(changes: SimpleChanges): Promise<void> {
    const modeChange = changes['activeMode'];
    if (!modeChange || modeChange.firstChange) {
      return;
    }
    if (this.isSpyker) {
      this.closeSuperServerDisclosure();
    }
    await this.ensureGraphForMode(this.activeMode);
    await this.loadPresetsForCurrentArchitecture();
  }

  public get isSpyker(): boolean {
    return this.activeMode === 'spyker';
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

  public setView(view: WorkspaceView): void {
    if (this.activeView === view) {
      return;
    }
    this.viewChange.emit(view);
  }

  public toggleArchitectureMenu(event?: Event): void {
    event?.stopPropagation();
    this.architectureMenuOpen = !this.architectureMenuOpen;
  }

  public closeArchitectureMenu(): void {
    this.architectureMenuOpen = false;
  }

  public architectureLabel(): string {
    return this.isSpyker ? 'Spyker' : 'Hierarchical';
  }

  public selectArchitectureMode(mode: Architecture, event?: Event): void {
    event?.stopPropagation();
    this.architectureMenuOpen = false;
    if (mode !== this.activeMode) {
      this.modeChange.emit(mode);
    }
  }

  @HostListener('document:click', ['$event'])
  public onDocumentClick(event: Event): void {
    const target = event.target as HTMLElement | null;
    if (!target?.closest('.architecture-select')) {
      this.architectureMenuOpen = false;
    }
  }

  private async ensureGraphForMode(mode: Architecture): Promise<void> {
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

  private currentArchitecture(): Architecture {
    return this.activeMode;
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

  private async loadPresetsForCurrentArchitecture(): Promise<void> {
    const architecture = this.currentArchitecture();
    try {
      await Promise.all(PRESET_KINDS.map((kind) => this.presets[kind].load(architecture)));
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

  public onDragStart(event: DragEvent, kind: NodeKind): void {
    // Node limits are enforced on drop; this only spares a pointless drag in Spyker.
    if (kind === 'SuperServerNode' && this.isSpyker) {
      event.preventDefault();
      event.stopPropagation();
      this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
      return;
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
  public openPresetPopup<K extends PresetKind>(kind: K): void {
    this.library(kind).openPopup(this.configDraft[kind]);
  }

  /** Selects a preset; its settings become the ones the next dragged node gets. */
  public selectPreset<K extends PresetKind>(kind: K, index: number): void {
    const config = this.library(kind).select(index);
    if (config) {
      this.setConfig(kind, config);
    }
  }

  public async savePresetDraft<K extends PresetKind>(kind: K): Promise<void> {
    try {
      const item = await this.library(kind).saveDraft(this.currentArchitecture());
      this.setConfig(kind, item.config);
      this.showSuccessToast(`Saved preset "${item.name}".`);
    } catch {
      this.showErrorToast(`Could not save ${PRESET_LABELS[kind].preset} preset.`);
    }
  }

  public async createDefaultPreset<K extends PresetKind>(kind: K): Promise<void> {
    try {
      const item = await this.library(kind).createDefault(this.currentArchitecture());
      this.setConfig(kind, item.config);
      this.showSuccessToast(`Created preset "${item.name}".`);
    } catch {
      this.showErrorToast(`Could not create ${PRESET_LABELS[kind].preset} preset.`);
    }
  }

  /** Saves the sidebar settings: asks before overwriting a selected preset. */
  public async saveCurrentPreset(kind: PresetKind): Promise<void> {
    const library = this.presets[kind];
    if (library.selected && library.selectedIndex !== null) {
      this.savePresetTarget = { kind, index: library.selectedIndex, name: library.selected.name };
      this.showConfirmSavePresetPopup = true;
      return;
    }
    await this.createPresetFromSettings(kind);
  }

  /** Takes over the selected preset for newly dragged nodes. */
  public usePreset(kind: PresetKind): void {
    const library = this.presets[kind];
    const label = PRESET_LABELS[kind];
    if (library.selectedIndex === null) {
      this.showErrorToast(`Select a ${label.preset} preset first.`);
      return;
    }
    if (kind === 'superserver' && this.isSpyker) {
      this.showErrorToast('No super server is allowed to exist in the Spyker Environment');
      return;
    }
    this.selectPreset(kind, library.selectedIndex);
    library.closePopup();
    this.showSuccessToast(`"${library.selectedName}" is now selected. Drag a ${label.node} node to place it.`);
  }

  public requestDeletePreset(kind: PresetKind, index: number): void {
    const item = this.presets[kind].items[index];
    if (item) {
      this.deletePresetTarget = { kind, index, name: item.name };
      this.showDeletePresetPopup = true;
    }
  }

  public closeDeletePresetPopup(): void {
    this.showDeletePresetPopup = false;
    this.deletePresetTarget = null;
  }

  public closeConfirmSavePresetPopup(): void {
    this.showConfirmSavePresetPopup = false;
    this.savePresetTarget = null;
  }

  public async confirmUpdateSelectedPreset(): Promise<void> {
    if (!this.savePresetTarget) {
      return;
    }
    const { kind } = this.savePresetTarget;
    try {
      const item = await this.updateSelectedPreset(kind);
      this.closeConfirmSavePresetPopup();
      if (item) {
        this.showSuccessToast(`Updated preset "${item.name}".`);
      }
    } catch {
      this.showErrorToast('Could not update preset.');
    }
  }

  public async confirmCreateNewPresetFromSidebar(): Promise<void> {
    if (!this.savePresetTarget) {
      return;
    }
    const { kind } = this.savePresetTarget;
    this.closeConfirmSavePresetPopup();
    await this.createPresetFromSettings(kind);
  }

  public async confirmDeletePreset(): Promise<void> {
    if (!this.deletePresetTarget) {
      return;
    }
    const { kind, index } = this.deletePresetTarget;
    try {
      await this.presets[kind].remove(index);
      this.closeDeletePresetPopup();
      this.showSuccessToast('Preset deleted.');
    } catch {
      this.showErrorToast('Could not delete preset.');
    }
  }

  private updateSelectedPreset<K extends PresetKind>(kind: K) {
    return this.library(kind).updateSelected(this.configDraft[kind]);
  }

  private async createPresetFromSettings<K extends PresetKind>(kind: K): Promise<void> {
    try {
      const item = await this.library(kind).saveConfig(this.currentArchitecture(), this.configDraft[kind]);
      this.showSuccessToast(`Saved preset "${item.name}".`);
    } catch {
      this.showErrorToast(`Could not save ${PRESET_LABELS[kind].preset} preset.`);
    }
  }

  private library<K extends PresetKind>(kind: K): PresetLibrary<PresetConfigs[K]> {
    return this.presets[kind];
  }

  private setConfig<K extends PresetKind>(kind: K, config: PresetConfigs[K]): void {
    this.configDraft[kind] = { ...config };
  }

  public onSuperServerSummaryClick(event: Event): void {
    if (this.isSpyker) {
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

  public onGraphSelected(event: { graphId: number; architecture: Architecture }): void {
    this.graphSelected.emit(event);
    this.closeViewGraphsDialog();
  }

  public runSimulation(payload: SimulationRequest): void {
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
    const openLibrary = PRESET_KINDS.map((kind) => this.presets[kind]).find((library) => library.popupOpen);
    if (openLibrary) {
      openLibrary.closePopup();
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
