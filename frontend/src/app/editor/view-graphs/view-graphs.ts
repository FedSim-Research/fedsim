import { Component, inject, Output, EventEmitter, OnInit, Input, OnChanges, SimpleChanges } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { GraphApiService, GraphResponse } from '../../api/graph-api.service';
import { ToastModule } from 'primeng/toast';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';
import { ListboxModule } from 'primeng/listbox';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { ConfirmationService, MessageService } from 'primeng/api';
import { ConfirmDialogModule } from 'primeng/confirmdialog';
import { Shortcuts } from '../shortcuts.directive';
import { graphFileFromDetail, graphFileName } from '../graph-file';
import { downloadJson } from '../../shared/download';
import { Architecture } from '../../domain/topology';

@Component({
  selector: 'app-view-graphs-dialog',
  standalone: true,
  templateUrl: './view-graphs.html',
  styleUrls: ['./view-graphs.css'],
  imports: [CommonModule, FormsModule, ToastModule, DialogModule, ButtonModule, ListboxModule, ProgressSpinnerModule, ConfirmDialogModule],
  providers: [MessageService],
})
export class ViewGraphsDialog implements OnInit, OnChanges {
  private graphApiService = inject(GraphApiService);
  private messageService = inject(MessageService);
  private confirmationService = inject(ConfirmationService);

  @Input() isDarkMode = true;
  @Input() shortcuts?: Shortcuts;
  @Input() activeMode: Architecture = 'hierfl';
  public graphs: GraphResponse[] = [];
  public isLoading = true;
  public selectedGraph: GraphResponse | null = null;
  public visible = true;
  public editingGraphId: number | null = null;
  public editingName = '';
  public createName = 'New Graph';
  public selectedMode: Architecture = 'hierfl';

  @Output() graphSelected = new EventEmitter<{ graphId: number; architecture: Architecture }>();
  @Output() close = new EventEmitter<void>();
  @Output() modeRequested = new EventEmitter<Architecture>();
  @Output() graphDeleted = new EventEmitter<{ graphId: number; architecture: Architecture }>();

  public ngOnInit(): void {
    this.selectedMode = this.activeMode;
    this.loadGraphs();
  }

  public ngOnChanges(changes: SimpleChanges): void {
    if (changes['activeMode']?.currentValue) {
      this.selectedMode = changes['activeMode'].currentValue;
    }
  }

  private async loadGraphs(): Promise<void> {
    try {
      this.graphs = await this.graphApiService.listGraphs();
    } catch (error) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to load graphs',
      });
    } finally {
      this.isLoading = false;
    }
  }

  public onLoadGraph(): void {
    if (!this.selectedGraph) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Warning',
        detail: 'Please select a graph',
      });
      return;
    }
    if (this.selectedGraph.architecture !== this.selectedMode) {
      this.messageService.add({
        severity: 'warn',
        summary: 'Warning',
        detail: `Select a ${this.selectedMode} graph to load`,
      });
      return;
    }

    this.graphSelected.emit({
      graphId: this.selectedGraph.graph_id,
      architecture: this.selectedGraph.architecture,
    });
    this.onClose();
  }

  public onClose(): void {
    if (!this.hasGraphsForMode(this.selectedMode)) {
      return;
    }
    this.visible = false;
    this.close.emit();
  }

  public async onExport(): Promise<void> {
    const graph = this.selectedGraph;
    if (!graph) {
      this.messageService.add({ severity: 'warn', summary: 'Warning', detail: 'Please select a graph to export' });
      return;
    }
    try {
      const detail = await this.graphApiService.getGraph(graph.graph_id);
      downloadJson(graphFileFromDetail(detail), graphFileName(graph.graph_id, graph.name, graph.architecture));
    } catch {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: 'Failed to export graph' });
    }
  }

  public async onImport(): Promise<void> {
    if (this.shortcuts) {
      try {
        await this.shortcuts.importGraph();
        this.onClose();
      } catch (error) {
        console.log("Error importing:", error);
      }
    }
  }

  public graphsForMode(mode: Architecture): GraphResponse[] {
    return this.graphs.filter((graph) => graph.architecture === mode);
  }

  public hasGraphsForMode(mode: Architecture): boolean {
    return this.graphsForMode(mode).length > 0;
  }

  public currentGraphLabel(mode: Architecture): string {
    const stored = localStorage.getItem(`fedsim.graphId.${mode}`);
    const id = stored ? Number(stored) : null;
    if (!id || !Number.isFinite(id)) return 'None';
    const graph = this.graphs.find((item) => item.graph_id === id);
    if (!graph) return 'None';
    return graph.name ? `${graph.name}` : `Graph ${id}`;
  }

  public async createEmptyGraph(): Promise<void> {
    const name = this.createName.trim() || 'New Graph';
    try {
      const created = await this.graphApiService.createGraph({
        name,
        architecture: this.selectedMode,
        metadata: null,
      });
      this.graphs = [created, ...this.graphs];
      this.selectedGraph = created;
      this.editingGraphId = created.graph_id;
      this.editingName = created.name ?? '';
    } catch {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to create graph',
      });
    }
  }

  public setMode(mode: Architecture): void {
    this.selectedMode = mode;
    this.modeRequested.emit(mode);
  }

  public startRename(graph: GraphResponse, event?: Event): void {
    event?.stopPropagation();
    this.editingGraphId = graph.graph_id;
    this.editingName = graph.name ?? '';
  }

  public async saveRename(graph: GraphResponse, event?: Event): Promise<void> {
    event?.stopPropagation();
    if (this.editingGraphId !== graph.graph_id) return;
    const trimmed = this.editingName.trim();
    if (!trimmed || trimmed === graph.name) {
      this.editingGraphId = null;
      return;
    }
    try {
      const updated = await this.graphApiService.renameGraph(graph.graph_id, { name: trimmed });
      this.graphs = this.graphs.map((item) =>
        item.graph_id === graph.graph_id ? { ...item, name: updated.name } : item
      );
      if (this.selectedGraph?.graph_id === graph.graph_id) {
        this.selectedGraph = { ...this.selectedGraph, name: updated.name };
      }
    } catch {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to rename graph',
      });
    } finally {
      this.editingGraphId = null;
    }
  }

  public cancelRename(event?: Event): void {
    event?.stopPropagation();
    this.editingGraphId = null;
  }

  public deleteGraph(graph: GraphResponse, event?: Event): void {
    event?.stopPropagation();
    this.confirmationService.confirm({
      key: 'graph-delete',
      header: 'Delete graph',
      message: `Delete "${graph.name ?? `Graph ${graph.graph_id}`}" with all its nodes and edges? This cannot be undone.`,
      acceptLabel: 'Delete',
      rejectLabel: 'Cancel',
      acceptButtonStyleClass: 'p-button-danger',
      rejectButtonStyleClass: 'p-button-text',
      accept: () => void this.confirmDeleteGraph(graph),
    });
  }

  private async confirmDeleteGraph(graph: GraphResponse): Promise<void> {
    try {
      await this.graphApiService.deleteGraph(graph.graph_id);
      this.graphDeleted.emit({ graphId: graph.graph_id, architecture: graph.architecture });
      this.graphs = this.graphs.filter((item) => item.graph_id !== graph.graph_id);
      if (this.selectedGraph?.graph_id === graph.graph_id) {
        this.selectedGraph = null;
      }
      if (this.editingGraphId === graph.graph_id) {
        this.editingGraphId = null;
      }
    } catch {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'Failed to delete graph',
      });
    }
  }
}
