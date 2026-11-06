import { Component, computed, inject } from '@angular/core';
import { NgIf } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { CustomNodeComponent, HandleComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../node-delete-ui.service';
import { HierflGraphService } from '../../topologies/hierfl-graph.service';
import { SpykerGraphService } from '../../topologies/spyker-graph.service';
import { NodeEditUiService } from '../../node-edit-ui.service';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-client-node',
  standalone: true,
  imports: [NgIf, HandleComponent, ButtonModule],
  templateUrl: './client-node.html',
  styleUrl: './client-node.css',
})

export class ClientNode extends CustomNodeComponent {
  protected graphServiceSpyker = inject(SpykerGraphService);
  protected graphServiceHierfl = inject(HierflGraphService);
  private nodeDeleteUi = inject(NodeDeleteUiService);
  private nodeEditUi = inject(NodeEditUiService);
  private messageService = inject(MessageService);
  private readonly defaults = {
    count: 50,
    computeFactor: 0.8,
    performanceSigma: 0,
    uploadMbps: 2,
    downloadMbps: 10,
  } as const;
  public isEditing = computed(() => this.nodeEditUi.activeId() === this.node().id);
  public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id || this.isEditing());
  public editDraft = computed(() =>
    this.nodeEditUi.getDraft(this.node().id, {
      count: Number(this.client().count ?? 50),
      type: String(this.client().type ?? ''),
      computeFactor: Number(this.client().computeFactor ?? 0.8),
      performanceSigma: Number(this.client().performanceSigma ?? 0),
      uploadMbps: Number(this.client().uploadMbps ?? 2),
      downloadMbps: Number(this.client().downloadMbps ?? 10),
    })
  );

  public isSelected = computed(() => Boolean((this.node().data as any)?.selected));

  public client = computed(() => {
    const config = ((this.node().data as any)?.config) ?? {};
    const environment = ((this.node().data as any)?.environment) ?? (config.environment ?? 'spyker');

    const rawType = config.type ?? '';
    const type = typeof rawType === 'string' && rawType.length
      ? rawType.charAt(0).toUpperCase() + rawType.slice(1)
      : rawType;

    return {
      id: config.id ?? '',
      count: config.count ?? 50,
      type,
      computeFactor: config.computeFactor ?? 0.8,
      performanceSigma: config.performanceSigma ?? 0.0,
      uploadMbps: config.uploadMbps ?? 2,
      downloadMbps: config.downloadMbps ?? 10,
      environment,
    };
  });

  public onNodeClick(event: MouseEvent): void {
    if (event.button !== 0) return;
    if (this.isEditing()) {
      event.stopPropagation();
      return;
    }
    if (event.ctrlKey || event.metaKey) {
      event.stopPropagation();
      window.dispatchEvent(new CustomEvent('node-ctrl-click', { detail: { id: this.node().id } }));
      return;
    }
    event.stopPropagation();
    this.nodeDeleteUi.showFor(this.node().id);
  }

  public onDelete(event: MouseEvent): void {
    event.stopPropagation();
    if (this.graphServiceSpyker.nodes().some(node => node.id === this.node().id)) {
      this.graphServiceSpyker.removeNodeById(this.node().id);
      console.log("Removed client node from spyker");
    } else {
      this.graphServiceHierfl.removeNodeById(this.node().id);
      console.log("Removed client node from hierfl");
    }
  }

  public onForwardNode(event: MouseEvent): void {
    event.stopPropagation();
    const current = this.client();
    window.dispatchEvent(new CustomEvent('node-forward', {
      detail: {
        kind: 'client',
        config: {
          ...current,
          type: String(current.type ?? '').toLowerCase(),
        },
      },
    }));
  }

  public onStartEdit(event: MouseEvent): void {
    event.stopPropagation();
    const current = this.client();
    this.nodeEditUi.startEditing(this.node().id, {
      count: Number(current.count ?? 50),
      type: String(current.type ?? ''),
      computeFactor: Number(current.computeFactor ?? 0.8),
      performanceSigma: Number(current.performanceSigma ?? 0),
      uploadMbps: Number(current.uploadMbps ?? 2),
      downloadMbps: Number(current.downloadMbps ?? 10),
    });
  }

  public onSaveEdit(event: MouseEvent): void {
    event.stopPropagation();
    const current = this.client();
    const draft = this.nodeEditUi.getDraft(this.node().id, {
      count: Number(current.count ?? 50),
      type: String(current.type ?? ''),
      computeFactor: Number(current.computeFactor ?? 0.8),
      performanceSigma: Number(current.performanceSigma ?? 0),
      uploadMbps: Number(current.uploadMbps ?? 2),
      downloadMbps: Number(current.downloadMbps ?? 10),
    });
    const nextConfig = {
      count: this.toNumber(draft.count, Number(current.count ?? 50)),
      type: String(draft.type ?? '').trim(),
      computeFactor: this.toNumber(draft.computeFactor, Number(current.computeFactor ?? 0.8)),
      performanceSigma: this.toNumber(draft.performanceSigma, Number(current.performanceSigma ?? 0)),
      uploadMbps: this.toNumber(draft.uploadMbps, Number(current.uploadMbps ?? 2)),
      downloadMbps: this.toNumber(draft.downloadMbps, Number(current.downloadMbps ?? 10)),
    };

    if (this.graphServiceSpyker.nodes().some((node) => node.id === this.node().id)) {
      this.graphServiceSpyker.updateNodeConfig(this.node().id, nextConfig);
    } else {
      this.graphServiceHierfl.updateNodeConfig(this.node().id, nextConfig);
    }
    this.nodeEditUi.stopEditing(this.node().id);
    this.nodeEditUi.clearDraft(this.node().id);
  }

  public updateTextField(field: 'type', event: Event): void {
    const value = (event.target as HTMLInputElement | HTMLSelectElement).value;
    this.nodeEditUi.updateDraft(this.node().id, { [field]: value });
  }

  public updateNumberField(
    field: 'count' | 'computeFactor' | 'performanceSigma' | 'uploadMbps' | 'downloadMbps',
    event: Event
  ): void {
    const input = event.target as HTMLInputElement;
    const value = Number(input.value);
    if (Number.isFinite(value) && value < 0) {
      const fallback = this.defaults[field];
      input.value = String(fallback);
      this.nodeEditUi.updateDraft(this.node().id, { [field]: fallback });
      this.showInvalidNumberToast();
      return;
    }
    if (!Number.isFinite(value)) {
      return;
    }
    this.nodeEditUi.updateDraft(this.node().id, { [field]: value });
  }

  private toNumber(value: number, fallback: number): number {
    return Number.isFinite(value) ? value : fallback;
  }

  private showInvalidNumberToast(): void {
    this.messageService.add({
      severity: 'warn',
      summary: 'Invalid value',
      detail: 'Negative values are not allowed. Value reset to default.',
    });
  }
}
