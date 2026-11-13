import { Directive, computed, inject } from '@angular/core';
import { CustomNodeComponent } from 'ngx-vflow';
import { MessageService } from 'primeng/api';
import { Architecture } from '../../domain/topology';
import { GraphWorkspace } from '../graph-workspace.service';
import { NodeDeleteUiService } from '../node-delete-ui.service';
import { NodeEditUiService } from '../node-edit-ui.service';

/** Flat, editable node settings; their defaults also define the edit form. */
export type NodeSettings = Record<string, string | number>;

export type ForwardKind = 'client' | 'server' | 'superserver';

interface NodeData {
  config?: Record<string, unknown>;
  environment?: Architecture;
  selected?: boolean;
}

/** Shared behaviour of canvas nodes: selection, inline editing, deletion and forwarding. */
@Directive()
export abstract class GraphNodeComponent<S extends NodeSettings> extends CustomNodeComponent<NodeData> {
  /** Editable settings and the value each falls back to. */
  protected abstract readonly defaults: S;
  /** Sidebar section that receives this node's settings when forwarded. */
  protected abstract readonly forwardKind: ForwardKind;

  private readonly workspace = inject(GraphWorkspace);
  private readonly deleteUi = inject(NodeDeleteUiService);
  private readonly editUi = inject(NodeEditUiService);
  private readonly messages = inject(MessageService);

  public readonly isEditing = computed(() => this.editUi.activeId() === this.node().id);
  public readonly showDelete = computed(() => this.deleteUi.activeId() === this.node().id || this.isEditing());
  public readonly isSelected = computed(() => Boolean(this.data()?.selected));
  public readonly environment = computed<Architecture>(() => this.data()?.environment ?? 'spyker');

  /** The node's settings, completed with defaults. */
  public readonly settings = computed(() => this.withDefaults(this.data()?.config ?? {}));
  public readonly editDraft = computed(() => this.editUi.getDraft(this.node().id, this.settings()));

  public onNodeClick(event: MouseEvent): void {
    if (event.button !== 0) return;
    event.stopPropagation();
    if (this.isEditing()) return;
    if (event.ctrlKey || event.metaKey) {
      window.dispatchEvent(new CustomEvent('node-ctrl-click', { detail: { id: this.node().id } }));
      return;
    }
    this.deleteUi.showFor(this.node().id);
  }

  public onDelete(event: MouseEvent): void {
    event.stopPropagation();
    this.graph().removeNodeById(this.node().id);
  }

  public onForwardNode(event: MouseEvent): void {
    event.stopPropagation();
    window.dispatchEvent(new CustomEvent('node-forward', {
      detail: { kind: this.forwardKind, config: this.settings() },
    }));
  }

  public onStartEdit(event: MouseEvent): void {
    event.stopPropagation();
    this.editUi.startEditing(this.node().id, { ...this.settings() });
  }

  public onSaveEdit(event: MouseEvent): void {
    event.stopPropagation();
    const id = this.node().id;
    this.graph().updateNodeConfig(id, this.toConfig(this.editDraft()));
    this.editUi.stopEditing(id);
    this.editUi.clearDraft(id);
  }

  public updateTextField(field: keyof S & string, event: Event): void {
    const value = (event.target as HTMLInputElement | HTMLSelectElement).value;
    this.editUi.updateDraft(this.node().id, { [field]: value });
  }

  public updateNumberField(field: keyof S & string, event: Event): void {
    const input = event.target as HTMLInputElement;
    const value = Number(input.value);
    if (!Number.isFinite(value)) {
      return;
    }
    if (value < 0) {
      const fallback = this.defaults[field];
      input.value = String(fallback);
      this.editUi.updateDraft(this.node().id, { [field]: fallback });
      this.messages.add({
        severity: 'warn',
        summary: 'Invalid value',
        detail: 'Negative values are not allowed. Value reset to default.',
      });
      return;
    }
    this.editUi.updateDraft(this.node().id, { [field]: value });
  }

  public formatNumber(value: number): string {
    if (!Number.isFinite(value)) return '0';
    return value.toLocaleString('en-US', { useGrouping: false, maximumFractionDigits: 6 });
  }

  /** Turns an edit draft into the config patch that is stored. Override to normalise values. */
  protected toConfig(draft: S): Partial<S> {
    const current = this.settings();
    const config: NodeSettings = {};
    for (const key of Object.keys(this.defaults)) {
      const value = draft[key];
      config[key] = typeof this.defaults[key] === 'number'
        ? (Number.isFinite(Number(value)) ? Number(value) : current[key])
        : String(value ?? '').trim();
    }
    return config as Partial<S>;
  }

  private withDefaults(config: Record<string, unknown>): S {
    const settings: NodeSettings = {};
    for (const [key, fallback] of Object.entries(this.defaults)) {
      const value = config[key];
      if (typeof fallback === 'number') {
        const numeric = Number(value);
        settings[key] = value === null || value === undefined || !Number.isFinite(numeric) ? fallback : numeric;
      } else {
        settings[key] = typeof value === 'string' ? value : fallback;
      }
    }
    return settings as S;
  }

  private graph() {
    return this.workspace.graphFor(this.environment());
  }
}
