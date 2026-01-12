import { Component, inject, Output, EventEmitter, OnInit, Input } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { GraphApiService, GraphResponse } from '../../services/graph-api.service';
import { ToastModule } from 'primeng/toast';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';
import { ListboxModule } from 'primeng/listbox';
import { ProgressSpinnerModule } from 'primeng/progressspinner';
import { MessageService } from 'primeng/api';
import { Shortcuts } from '../../directives/shortcuts';

@Component({
  selector: 'app-view-graphs-dialog',
  standalone: true,
  templateUrl: './view-graphs.component.html',
  styleUrls: ['./view-graphs.component.css'],
  imports: [CommonModule, FormsModule, ToastModule, DialogModule, ButtonModule, ListboxModule, ProgressSpinnerModule],
  providers: [MessageService],
})
export class ViewGraphsDialog implements OnInit {
  private graphApiService = inject(GraphApiService);
  private messageService = inject(MessageService);

  @Input() isDarkMode = true;
  @Input() shortcuts?: Shortcuts;
  public graphs: GraphResponse[] = [];
  public isLoading = true;
  public selectedGraph: GraphResponse | null = null;
  public visible = true;
  public editingGraphId: number | null = null;
  public editingName = '';

  @Output() graphSelected = new EventEmitter<{ graphId: number; architecture: 'spyker' | 'hierfl' }>();
  @Output() close = new EventEmitter<void>();

  public ngOnInit(): void {
    this.loadGraphs();
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

    this.graphSelected.emit({
      graphId: this.selectedGraph.graph_id,
      architecture: this.selectedGraph.architecture,
    });
    this.onClose();
  }

  public onClose(): void {
    this.visible = false;
    this.close.emit();
  }

  public onExport(): void {
    if (this.shortcuts) {
      this.shortcuts.exportGraph();
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
}
