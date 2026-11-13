import { Directive, HostListener, inject, ElementRef, input, effect, untracked } from '@angular/core';
import { ArchitectureGraph } from './graph-workspace.service';
import { StaticEdge as Edge } from 'ngx-vflow';
import { MessageService } from 'primeng/api';
import type { OnSelect, OnSelectEnd, OnDragStart as SelectoDragStart } from 'selecto';
import { v4 as uuidv4 } from 'uuid';
import { GRAPH_FILE_LIMITS, GraphFileError, parseGraphFile } from './graph-file';
import { createGraphNode } from './nodes/node-factory';
import { NodeKind } from '../domain/topology';
import { nodeLimitViolation } from '../domain/node-limits';


/** Offset of pasted nodes from their originals, in canvas units. */
const PASTE_OFFSET = 50;

interface CopiedNode {
  kind: NodeKind;
  point: { x: number; y: number };
  config: Record<string, unknown>;
}

@Directive({
  selector: '[appShortcuts]',
  standalone: true,
  exportAs: 'appShortcuts',
})
export class Shortcuts{
  protected messageService = inject(MessageService);
  protected elRef = inject(ElementRef) as ElementRef<HTMLElement>;
  public activeService = input.required<ArchitectureGraph>();
  private clipboard: CopiedNode[] = [];
  public selectedNodeIds: Set<string> = new Set();
  public selectedEdgeIds: Set<string> = new Set();
  public shiftDown = false;
  private selecting = false;
  private lastSelectElements: Array<HTMLElement | SVGElement> = [];

  constructor() {
    // A selection only makes sense inside the graph it was made in.
    let previous: ArchitectureGraph | null = null;
    effect(() => {
      const current = this.activeService();
      untracked(() => {
        previous?.setSelection(new Set(), new Set());
        this.clearSelectionState();
        previous = current;
      });
    });
  }

  @HostListener('window:keydown', ['$event'])
  public onKeyDown(event: KeyboardEvent): void {
    const isTypingTarget = this.isEditableTarget(event.target);

    if (event.key === 'Shift') {
      this.shiftDown = true;
    }
    if (!isTypingTarget && event.key === 'Escape') {
      event.preventDefault();
      this.clearNodeSelection();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && !isTypingTarget) {
      const key = event.key.toLowerCase();
      if (key === 'z') {
        event.preventDefault();
        this.applyHistoryAction('undo');
        return;
      }
      if (key === 'y') {
        event.preventDefault();
        this.applyHistoryAction('redo');
        return;
      }
      if (key === 'c') {
        event.preventDefault();
        this.copySelectedNodes();
        return;
      }
      if (key === 'v') {
        event.preventDefault();
        this.pasteCopiedNodes();
        return;
      }
    }
    if (isTypingTarget) {
      return;
    }
    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (!this.selectedEdgeIds.size && !this.selectedNodeIds.size) return;
      event.preventDefault();
      this.activeService().removeEntities(this.selectedNodeIds, this.selectedEdgeIds);
      this.selectedNodeIds.clear();
      this.selectedEdgeIds.clear();
    }
  }

  private isEditableTarget(target: EventTarget | null): boolean {
    const element = target instanceof Element ? target : null;
    if (!element) {
      return false;
    }
    return Boolean(
      element.closest('input, textarea, [contenteditable="true"], [contenteditable=""]')
    );
  }

  @HostListener('document:keyup', ['$event'])
  public onKeyUp(event: KeyboardEvent) {
    if (event.key === 'Shift') {
      this.shiftDown = false;
      if (this.selecting) {
        this.applySelectionFromElements(this.lastSelectElements);
        this.resetBoxSelectionState();
      }
    }
  }

  @HostListener('document:pointerdown', ['$event'])
  public onPointerDown(event: PointerEvent) {
    if (event.button !== 0) return;
    if (this.shiftDown) return;

    const target = event.target as Element | null;
    if (!target) return;
    const hostEl = this.elRef.nativeElement;
    if (!hostEl.contains(target)) return;
    if (this.findNodeId(target)) return;
    if (target.closest('app-sidebar')) return;
    if (target.closest('.selecto-selection')) return;
    if (!this.selectedNodeIds.size && !this.selectedEdgeIds.size) return;
    this.clearNodeSelection();
  }

  public onSelectoDragStart(event: SelectoDragStart) {
    const input = event.inputEvent as PointerEvent | MouseEvent | TouchEvent | undefined;

    const targetEl = (input && 'target' in input) ? (input as any).target as Element | null : null;
    if (targetEl && targetEl.closest('app-sidebar')) {
      event.stop();
      return;
    }

    if (!this.shiftDown) {
      event.stop();
      return;
    }
    this.selecting = true;
    this.lastSelectElements = [];
  }

  public onSelectoSelect(event: OnSelect) {
    if (!this.shiftDown) return;
    this.lastSelectElements = event.selected;
  }

  public onSelectoSelectEnd(event: OnSelectEnd) {
    this.lastSelectElements = event.selected;
    this.applySelectionFromElements(event.selected);
    this.resetBoxSelectionState();
  }

  @HostListener('window:node-ctrl-click', ['$event'])
  public onNodeCtrlClick(event: Event): void {
    const custom = event as CustomEvent<any>;
    const id = custom?.detail?.id as string | undefined;
    if (!id) return;
    const selected = new Set(this.selectedNodeIds);
    if (selected.has(id)) selected.delete(id);
    else selected.add(id);
    this.applySelection(selected);
  }

  private applySelection(selected: Set<string>): void {
    this.selectedNodeIds = new Set(selected);
    this.selectedEdgeIds = new Set(
      this.activeService()
        .edges()
        .filter((edge) => selected.has(edge.source) && selected.has(edge.target))
        .map((edge) => edge.id),
    );
    this.activeService().setSelection(this.selectedNodeIds, this.selectedEdgeIds);
  }


  private applySelectionFromElements(elements: Array<HTMLElement | SVGElement>) {
    const nodeIds = this.extractNodeIds(elements);
    if (!nodeIds.size) {
      this.clearNodeSelection();
      return;
    }
    this.applySelection(nodeIds);
  }

  private extractNodeIds(elements: Array<HTMLElement | SVGElement>): Set<string> {
    const ids = new Set<string>();
    elements.forEach((el) => {
      const id = this.findNodeId(el as Element);
      if (id) ids.add(id);
    });
    return ids;
  }

  private findNodeId(element: Element | null): string | null {
    let current: Element | null = element;
    while (current) {
      const dataset = (current as HTMLElement).dataset;
      const candidate = dataset?.['id'] || dataset?.['nodeId'] || current.getAttribute('data-id') || current.getAttribute('data-node-id');
      if (candidate) return candidate;
      current = current.parentElement;
    }
    return null;
  }

  private resetBoxSelectionState() {
    this.selecting = false;
    this.lastSelectElements = [];
  }

  private clearNodeSelection(): void {
    this.selectedNodeIds = new Set();
    this.selectedEdgeIds = new Set();
    this.activeService().setSelection(this.selectedNodeIds, this.selectedEdgeIds);
  }


  public clearSelectionState(): void {
    this.clearNodeSelection();
    this.resetBoxSelectionState();
  }

  public copySelectedNodes(): void {
    this.clipboard = this.activeService()
      .nodes()
      .filter((node) => this.selectedNodeIds.has(node.id))
      .map((node) => {
        const data = (node as { data?: { type?: NodeKind; config?: Record<string, unknown> } }).data ?? {};
        return { kind: data.type!, point: { ...node.point }, config: { ...(data.config ?? {}) } };
      });
  }

  /** Pastes the copied nodes slightly offset, as one undoable step. */
  public pasteCopiedNodes(): void {
    if (!this.clipboard.length) return;
    const service = this.activeService();
    const nodes = this.clipboard.map((entry) => createGraphNode({
      id: uuidv4(),
      kind: entry.kind,
      architecture: service.architecture,
      point: { x: entry.point.x + PASTE_OFFSET, y: entry.point.y + PASTE_OFFSET },
      config: { ...entry.config, environment: service.architecture },
    }));
    const rejection = service.addEntities(nodes, []);
    if (rejection) {
      this.messageService.add({ severity: 'error', summary: 'Error', detail: rejection });
      return;
    }
    this.applySelection(new Set(nodes.map((node) => node.id)));
  }

  private applyHistoryAction(action: 'undo' | 'redo'): void {
    const service = this.activeService();
    const changed = action === 'undo' ? service.undo() : service.redo();
    if (changed) {
      this.clearSelectionState();
    }
  }

  public onEdgeSelectionChange(changes: Array<{ id: string; selected: boolean }>): void {
    const next = new Set(this.selectedEdgeIds);
    for (const change of changes) {
      if (!change?.id) continue;
      if (change.selected) {
        next.add(change.id);
      } else {
        next.delete(change.id);
      }
    }
    this.applyEdgeSelection(next);
  }

  private applyEdgeSelection(selectedEdges: Set<string>): void {
    this.selectedEdgeIds = new Set(selectedEdges);
    this.activeService().setSelection(this.selectedNodeIds, this.selectedEdgeIds);
  }


  public async importGraph(): Promise<void> {
    return new Promise((resolve, reject) => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = '.json,application/json';
      input.onchange = async (event: Event) => {
        const file = (event.target as HTMLInputElement).files?.[0];
        if (!file) {
          reject(new Error('No file selected'));
          return;
        }
        try {
          await this.importGraphFile(file);
          resolve();
        } catch (error) {
          const detail = error instanceof GraphFileError ? error.message : 'The file is not a valid graph export.';
          this.messageService.add({ severity: 'error', summary: 'Import failed', detail });
          reject(error);
        }
      };
      input.click();
    });
  }

  private async importGraphFile(file: File): Promise<void> {
    const service = this.activeService();
    const architecture = service.architecture;
    if (file.size > GRAPH_FILE_LIMITS.bytes) {
      throw new GraphFileError('The file is too large for a graph export.');
    }
    const graph = parseGraphFile(JSON.parse(await file.text()), uuidv4);
    const violation = nodeLimitViolation(architecture, [], graph.nodes.map((node) => node.kind));
    if (violation) {
      throw new GraphFileError(violation);
    }

    const nodes = graph.nodes.map((node) => createGraphNode({ ...node, architecture }));
    const edges: Edge[] = graph.edges.map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? undefined,
      targetHandle: edge.targetHandle ?? undefined,
      reconnectable: true,
      floating: false,
      data: { metrics: edge.metrics },
    }));

    service.replaceContents(nodes, edges);
  }
}
