import { Component, computed, inject } from '@angular/core';
import { NgIf } from '@angular/common';
import { ButtonModule } from 'primeng/button';
import { CustomNodeComponent, HandleComponent } from 'ngx-vflow';
import { NodeDeleteUiService } from '../../node-delete-ui.service';
import { SpykerGraphService } from '../../topologies/spyker-graph.service';
import { HierflGraphService } from '../../topologies/hierfl-graph.service';
import { NodeEditUiService } from '../../node-edit-ui.service';
import { MessageService } from 'primeng/api';

@Component({
  selector: 'app-server-node',
  standalone: true,
  imports: [NgIf, HandleComponent, ButtonModule],
  templateUrl: './server-node.html',
  styleUrl: './server-node.css',
})
export class ServerNode extends CustomNodeComponent {
  protected graphServiceSpyker = inject(SpykerGraphService);
  protected graphServiceHierfl = inject(HierflGraphService);
  private nodeDeleteUi = inject(NodeDeleteUiService);
  private nodeEditUi = inject(NodeEditUiService);
  private messageService = inject(MessageService);
  private readonly defaults = {
    computeFactor: 2,
    performanceSigma: 0,
    uploadMbps: 20,
    downloadMbps: 100,
  } as const;
  public isEditing = computed(() => this.nodeEditUi.activeId() === this.node().id);
  public showDelete = computed(() => this.nodeDeleteUi.activeId() === this.node().id || this.isEditing());
  public isSelected = computed(() => Boolean((this.data() as any)?.selected));
  public editDraft = computed(() =>
    this.nodeEditUi.getDraft(this.node().id, {
      name: String(this.server().name ?? ''),
      computeFactor: Number(this.server().computeFactor ?? 2),
      performanceSigma: Number(this.server().performanceSigma ?? 0),
      uploadMbps: Number(this.server().uploadMbps ?? 20),
      downloadMbps: Number(this.server().downloadMbps ?? 100),
    })
  );

  public server = computed(() => {
    const config = ((this.data() as any)?.config) ?? {};
    const environment = ((this.data() as any)?.environment) ?? (config.environment ?? 'spyker');
    return {
      name: config.name ?? '',
      id: config.id ?? '',
      computeFactor: config.computeFactor ?? 2.0,
      performanceSigma: config.performanceSigma ?? 0.0,
      uploadMbps: config.uploadMbps ?? 20,
      downloadMbps: config.downloadMbps ?? 100,
      environment,
    };
  });

  public environment = computed(() => (this.server().environment ?? 'spyker').toString().toLowerCase());

  public formatNumber(value: number): string {
    if (!Number.isFinite(value)) return '0';
    return value.toLocaleString('en-US', {
      useGrouping: false,
      maximumFractionDigits: 6,
    });
  }

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
      console.log("Removed server node from spyker");
    } else {
      this.graphServiceHierfl.removeNodeById(this.node().id);
      console.log("Removed server node from hierfl");
    }
  }

  public onForwardNode(event: MouseEvent): void {
    event.stopPropagation();
    window.dispatchEvent(new CustomEvent('node-forward', {
      detail: {
        kind: 'server',
        config: this.server(),
      },
    }));
  }

  public onStartEdit(event: MouseEvent): void {
    event.stopPropagation();
    const current = this.server();
    this.nodeEditUi.startEditing(this.node().id, {
      name: String(current.name ?? ''),
      computeFactor: Number(current.computeFactor ?? 2),
      performanceSigma: Number(current.performanceSigma ?? 0),
      uploadMbps: Number(current.uploadMbps ?? 20),
      downloadMbps: Number(current.downloadMbps ?? 100),
    });
  }

  public onSaveEdit(event: MouseEvent): void {
    event.stopPropagation();
    const current = this.server();
    const draft = this.nodeEditUi.getDraft(this.node().id, {
      name: String(current.name ?? ''),
      computeFactor: Number(current.computeFactor ?? 2),
      performanceSigma: Number(current.performanceSigma ?? 0),
      uploadMbps: Number(current.uploadMbps ?? 20),
      downloadMbps: Number(current.downloadMbps ?? 100),
    });
    const nextConfig = {
      name: String(draft.name ?? '').trim(),
      computeFactor: this.toNumber(draft.computeFactor, Number(current.computeFactor ?? 2)),
      performanceSigma: this.toNumber(draft.performanceSigma, Number(current.performanceSigma ?? 0)),
      uploadMbps: this.toNumber(draft.uploadMbps, Number(current.uploadMbps ?? 20)),
      downloadMbps: this.toNumber(draft.downloadMbps, Number(current.downloadMbps ?? 100)),
    };

    if (this.graphServiceSpyker.nodes().some((node) => node.id === this.node().id)) {
      this.graphServiceSpyker.updateNodeConfig(this.node().id, nextConfig);
    } else {
      this.graphServiceHierfl.updateNodeConfig(this.node().id, nextConfig);
    }
    this.nodeEditUi.stopEditing(this.node().id);
    this.nodeEditUi.clearDraft(this.node().id);
  }

  public updateTextField(field: 'name', event: Event): void {
    const value = (event.target as HTMLInputElement).value;
    this.nodeEditUi.updateDraft(this.node().id, { [field]: value });
  }

  public updateNumberField(
    field: 'computeFactor' | 'performanceSigma' | 'uploadMbps' | 'downloadMbps',
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
