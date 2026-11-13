import { Directive, HostListener, inject, ElementRef, input, effect, untracked } from '@angular/core';
import { HierflGraphService } from './topologies/hierfl-graph.service';
import { SpykerGraphService } from './topologies/spyker-graph.service';
import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { ClientNode } from './nodes/client-node/client-node';
import { ServerNode } from './nodes/server-node/server-node';
import { SuperServerNode } from './nodes/super-server-node/super-server-node';
import { MessageService } from 'primeng/api';
import type { OnSelect, OnSelectEnd, OnDragStart as SelectoDragStart } from 'selecto';
import { v4 as uuidv4 } from 'uuid';
import { GRAPH_FILE_LIMITS, GraphFileError, parseGraphFile } from './graph-file';


@Directive({
  selector: '[appShortcuts]',
  standalone: true,
  exportAs: 'appShortcuts',
})
export class Shortcuts{
  protected graphServiceSpyker = inject(SpykerGraphService);
  protected graphServiceHierfl = inject(HierflGraphService);
  protected messageService = inject(MessageService);
  protected elRef = inject(ElementRef) as ElementRef<HTMLElement>;
  public activeService = input.required<SpykerGraphService | HierflGraphService>();
  private readonly nodeTypeMap = {
    ClientNode,
    ServerNode,
    SuperServerNode,
  } as const;
  private clipboard: Node[] = [];
  public selectedNodeIds: Set<string> = new Set();
  public selectedEdgeIds: Set<string> = new Set();
  public shiftDown = false;
  private selecting = false;
  private lastSelectElements: Array<HTMLElement | SVGElement> = [];

  constructor() {
    // A selection only makes sense inside the graph it was made in.
    effect(() => {
      this.activeService();
      untracked(() => this.clearSelectionState());
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

  @HostListener('document:pointermove', ['$event'])
  public onPointerMove(event: PointerEvent) {
    if (!this.shiftDown || event.buttons !== 1) return;
  }

  @HostListener('document:pointerup', ['$event'])
  public onPointerUp(event: PointerEvent) {
    if (this.shiftDown && event.button === 0) {
    }
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

  private applySelection(selected: Set<string>) {
    this.selectedNodeIds = new Set(selected);
    const spykerNodes = this.graphServiceSpyker.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      const selectedFlag = selected.has(n.id);
      return { ...n, data: { ...data, selected: selectedFlag } } as Node;
    });
    this.graphServiceSpyker.nodes.set(spykerNodes);

    const hierNodes = this.graphServiceHierfl.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      const selectedFlag = selected.has(n.id);
      return { ...n, data: { ...data, selected: selectedFlag } } as Node;
    });
    this.graphServiceHierfl.nodes.set(hierNodes);
    this.applyEdgeSelection(this.collectSelectedEdges(selected));
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

  private collectSelectedEdges(selectedNodes: Set<string>): Set<string> {
    const ids = new Set<string>();

    const addEdges = (edges: any[]) => {
      edges.forEach((e) => {
        if (selectedNodes.has(e.source) && selectedNodes.has(e.target)) {
          ids.add(e.id);
        }
      });
    };

    addEdges(this.graphServiceSpyker.edges());
    addEdges(this.graphServiceHierfl.edges());

    return ids;
  }

  private clearNodeSelection() {
    this.selectedNodeIds.clear();
    const spykerCleared = this.graphServiceSpyker.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      if (data.selected) return { ...n, data: { ...data, selected: false } } as Node;
      return n;
    });
    this.graphServiceSpyker.nodes.set(spykerCleared);

    const hierCleared = this.graphServiceHierfl.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      if (data.selected) return { ...n, data: { ...data, selected: false } } as Node;
      return n;
    });
    this.graphServiceHierfl.nodes.set(hierCleared);
    this.applyEdgeSelection(new Set());
  }

  public clearSelectionState(): void {
    this.clearNodeSelection();
    this.resetBoxSelectionState();
  }

  public copySelectedNodes() {
    const ids = Array.from(this.selectedNodeIds);
    const copied: any[] = [];
    for (const id of ids) {
      const n1 = this.graphServiceSpyker.nodes().find((n) => n.id === id);
      const n2 = this.graphServiceHierfl.nodes().find((n) => n.id === id);
      const src = n1 ?? n2;
      if (src) {
        const { id, ...rest } = src;
        copied.push(JSON.parse(JSON.stringify(rest)));
      }
    }
    this.clipboard = copied;
  }

  public pasteCopiedNodes() {
    if (!this.clipboard.length) return;
    const targetArchitecture = this.activeService() instanceof HierflGraphService ? 'hierfl' : 'spyker';
    let blockedSuperServer = false;

    const newNodeIds = this.clipboard.flatMap((node) => {
      const typeString = ((node as any).data as any)?.type as keyof typeof this.nodeTypeMap | undefined;
      if (targetArchitecture === 'spyker' && typeString === 'SuperServerNode') {
        blockedSuperServer = true;
        return [];
      }
      const newNode = this.buildPastedNode(node, targetArchitecture, typeString);
      this.activeService().addNode(newNode);
      return [newNode.id];
    });

    if (blockedSuperServer) {
      this.messageService.add({
        severity: 'error',
        summary: 'Error',
        detail: 'No super server is allowed to exist in the Spyker Environment',
      });
    }

    if (newNodeIds.length) {
      this.applySelection(new Set(newNodeIds));
    }
  }

  private buildPastedNode(
    sourceNode: Node,
    targetArchitecture: 'spyker' | 'hierfl',
    typeString?: keyof typeof this.nodeTypeMap
  ): Node {
    const clone = JSON.parse(JSON.stringify(sourceNode));
    const data = ((clone as any).data as any) ?? {};
    const config = (data.config as Record<string, unknown> | undefined) ?? {};
    const nextData = {
      ...data,
      selected: false,
      fromJson: false,
      environment: targetArchitecture,
      config: {
        ...config,
        environment: targetArchitecture,
      },
    } as Record<string, unknown>;

    return {
      ...clone,
      id: uuidv4(),
      type: typeString ? this.nodeTypeMap[typeString] : undefined,
      point: { x: (sourceNode.point?.x ?? 0) + 50, y: (sourceNode.point?.y ?? 0) + 50 },
      data: nextData,
    };
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

    const spykerEdges = this.graphServiceSpyker.edges().map((e) => {
      const data = ((e as any).data as any) || {};
      const selectedFlag = selectedEdges.has(e.id);
      return { ...e, data: { ...data, selected: selectedFlag } } as any;
    });
    this.graphServiceSpyker.edges.set(spykerEdges);

    const hierEdges = this.graphServiceHierfl.edges().map((e) => {
      const data = ((e as any).data as any) || {};
      const selectedFlag = selectedEdges.has(e.id);
      return { ...e, data: { ...data, selected: selectedFlag } } as any;
    });
    this.graphServiceHierfl.edges.set(hierEdges);
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
    const architecture = service instanceof HierflGraphService ? 'hierfl' : 'spyker';
    if (file.size > GRAPH_FILE_LIMITS.bytes) {
      throw new GraphFileError('The file is too large for a graph export.');
    }
    const graph = parseGraphFile(JSON.parse(await file.text()), uuidv4);
    const superServers = graph.nodes.filter((node) => node.kind === 'SuperServerNode').length;
    if (superServers > (architecture === 'hierfl' ? 1 : 0)) {
      throw new GraphFileError(
        architecture === 'hierfl'
          ? 'A hierarchical graph can contain only one Super Server.'
          : 'Spyker graphs cannot contain a Super Server.',
      );
    }

    const nodes: Node[] = graph.nodes.map((node) => ({
      id: node.id,
      point: node.point,
      type: this.nodeTypeMap[node.kind],
      data: { type: node.kind, config: node.config, environment: architecture, fromJson: true, selected: false },
    }));
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
