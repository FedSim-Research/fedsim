import { Directive, HostListener, inject, ElementRef, input, ChangeDetectorRef} from '@angular/core';
import { GraphServiceHierach } from '../services/subservices/graph-service-hierach';
import { GraphServiceSpyker } from '../services/subservices/graph-service-spyker';
import { Node } from 'ngx-vflow';
import { ClientNode } from '../components/nodes/client-node/client-node';
import { ServerNode } from '../components/nodes/server-node/server-node';
import { SuperServerNode } from '../components/nodes/super-server-node/super-server-node';
import { MessageService } from 'primeng/api';
import type { OnSelect, OnSelectEnd, OnDragStart as SelectoDragStart } from 'selecto';
import { GraphPersistenceService } from '../services/graph-persistence.service';


@Directive({
  selector: '[appShortcuts]',
  standalone: true,
  exportAs: 'appShortcuts',
})
export class Shortcuts{
  protected graphServiceSpyker = inject(GraphServiceSpyker);
  protected graphServiceHierach = inject(GraphServiceHierach);
  protected graphPersistence = inject(GraphPersistenceService);
  protected messageService = inject(MessageService);
  protected elRef = inject(ElementRef) as ElementRef<HTMLElement>;
  public activeService = input.required<GraphServiceSpyker | GraphServiceHierach>();
  private clipboard: Node[] = [];
  public selectedNodeIds: Set<string> = new Set();
  public selectedEdgeIds: Set<string> = new Set();
  public shiftDown = false;
  private selecting = false;
  private lastSelectElements: Array<HTMLElement | SVGElement> = [];

  @HostListener('window:keydown', ['$event'])
  public onKeyDown(event: KeyboardEvent): void {
    if (event.key === 'Shift') {
      this.shiftDown = true;
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      this.clearNodeSelection();
      return;
    }
    if (event.ctrlKey || event.metaKey) {
      const key = event.key.toLowerCase();
      if (key === 'z') {
        event.preventDefault();
        void this.applyHistoryAction('undo');
        return;
      }
      if (key === 'y') {
        event.preventDefault();
        void this.applyHistoryAction('redo');
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
    if (event.key === 'Delete' || event.key === 'Backspace') {
      if (!this.selectedEdgeIds.size && !this.selectedNodeIds.size) return;
      event.preventDefault();
      const edgeIds = Array.from(this.selectedEdgeIds);
      for (const edgeId of edgeIds) {
        if (this.graphServiceSpyker.edges().some((e) => e.id === edgeId)) {
          this.graphServiceSpyker.removeEdgeById(edgeId);
        } else if (this.graphServiceHierach.edges().some((e) => e.id === edgeId)) {
          this.graphServiceHierach.removeEdgeById(edgeId);
        }
      }
      this.selectedEdgeIds.clear();
      const nodeIds = Array.from(this.selectedNodeIds);
      for (const nodeId of nodeIds) {
        if (this.graphServiceSpyker.nodes().some((node) => node.id === nodeId)) {
          this.graphServiceSpyker.removeNodeById(nodeId);
        } else if (this.graphServiceHierach.nodes().some((node) => node.id === nodeId)) {
          this.graphServiceHierach.removeNodeById(nodeId);
        }
      }
      this.selectedNodeIds.clear();
    }
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
    const selectedEdges = this.collectSelectedEdges(selected);
    this.selectedEdgeIds = selectedEdges;
    const spykerNodes = this.graphServiceSpyker.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      const selectedFlag = selected.has(n.id);
      return { ...n, data: { ...data, selected: selectedFlag } } as Node;
    });
    this.graphServiceSpyker.nodes.set(spykerNodes);

    const hierNodes = this.graphServiceHierach.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      const selectedFlag = selected.has(n.id);
      return { ...n, data: { ...data, selected: selectedFlag } } as Node;
    });
    this.graphServiceHierach.nodes.set(hierNodes);

    const spykerEdges = this.graphServiceSpyker.edges().map((e) => {
      const data = ((e as any).data as any) || {};
      const selectedFlag = selectedEdges.has(e.id);
      return { ...e, data: { ...data, selected: selectedFlag } } as any;
    });
    this.graphServiceSpyker.edges.set(spykerEdges);

    const hierEdges = this.graphServiceHierach.edges().map((e) => {
      const data = ((e as any).data as any) || {};
      const selectedFlag = selectedEdges.has(e.id);
      return { ...e, data: { ...data, selected: selectedFlag } } as any;
    });
    this.graphServiceHierach.edges.set(hierEdges);
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
    addEdges(this.graphServiceHierach.edges());

    return ids;
  }

  private clearNodeSelection() {
    this.selectedNodeIds.clear();
    this.selectedEdgeIds.clear();
    const spykerCleared = this.graphServiceSpyker.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      if (data.selected) return { ...n, data: { ...data, selected: false } } as Node;
      return n;
    });
    this.graphServiceSpyker.nodes.set(spykerCleared);

    const hierCleared = this.graphServiceHierach.nodes().map((n) => {
      const data = ((n as any).data as any) || {};
      if (data.selected) return { ...n, data: { ...data, selected: false } } as Node;
      return n;
    });
    this.graphServiceHierach.nodes.set(hierCleared);
  }

  public copySelectedNodes() {
    const ids = Array.from(this.selectedNodeIds);
    const copied: any[] = [];
    for (const id of ids) {
      const n1 = this.graphServiceSpyker.nodes().find((n) => n.id === id);
      const n2 = this.graphServiceHierach.nodes().find((n) => n.id === id);
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
    const NODE_TYPE_MAP = {
      ClientNode, ServerNode, SuperServerNode
    } as const;

    const isSpyker = this.activeService() instanceof GraphServiceSpyker;
    let blockedSuperServer = false;

    const newNodeIds = this.clipboard.flatMap((node) => {
      const newId = crypto.randomUUID();
      const typeString = ((node as any).data as any)?.type;
      if (isSpyker && typeString === 'SuperServerNode') {
        blockedSuperServer = true;
        return [];
      }
      const newNode: Node = {
        ...JSON.parse(JSON.stringify(node)),
        id: newId,
        type: typeString ? NODE_TYPE_MAP[typeString as keyof typeof NODE_TYPE_MAP] : undefined,
        point: { x: (node.point?.x ?? 0) + 50, y: (node.point?.y ?? 0) + 50 },
      };
      this.activeService().addNode(newNode);
      return [newId];
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

  private async applyHistoryAction(action: 'undo' | 'redo'): Promise<void> {
    const service = this.activeService();
    if (!service) return;
    const history = service.getGraphHistory();
    const before = history.getState();
    if (action === 'undo') {
      history.undo();
    } else {
      history.redo();
    }
    const snapshot = history.getState();
    if (before === snapshot) return;
    service.nodes.set(snapshot.nodes);
    service.edges.set(snapshot.edges);
    const architecture = service instanceof GraphServiceHierach ? 'hierfl' : 'spyker';
    try {
      await this.graphPersistence.syncGraphState(service, architecture, false);
    } catch (error) {
      this.messageService.add({
        severity: 'error',
        summary: 'Sync failed',
        detail: 'Undo/redo could not be saved to the backend.',
      });
      console.warn('Undo/redo sync failed', error);
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
    this.selectedEdgeIds = next;
  }

  public exportGraph(options?: {
    graphId?: number | null;
    graphName?: string | null;
    architecture?: 'spyker' | 'hierfl';
  }) {
    const serializedNodes = this.activeService().nodes().map((node) => {
      const { type, ...rest } = node as any;
      return rest;
    });
    const serializedEdges = this.activeService().edges().map((edge) => ({
      ...edge
    }));
    const data = {
      nodes: serializedNodes,
      edges: serializedEdges,
      nodeCount: serializedNodes.length,
      edgeCount: serializedEdges.length
    };
    const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    const storedId = this.activeService().loadGraphIdFromStorage();
    const graphId = options?.graphId ?? storedId ?? 'graph';
    const rawName = options?.graphName ?? 'graph';
    const safeName = rawName
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-_]+/g, '')
      .slice(0, 48) || 'graph';
    const architecture =
      options?.architecture ??
      (this.activeService() instanceof GraphServiceHierach ? 'hierfl' : 'spyker');
    const filename = `${graphId}_${safeName}_${architecture}.json`;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
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
          const text = await file.text();
          const data = JSON.parse(text);
          if (!data.nodes || !Array.isArray(data.nodes)) {
            throw new Error('No nodes!');
          }
          const NODE_TYPE_MAP = {
            ClientNode, ServerNode, SuperServerNode
          } as const;
          this.activeService().resetGraph();
          for (const nodeData of data.nodes) {
            const typeString = nodeData.data?.type;
            const node: Node = {
              ...nodeData,
              id: nodeData.id,
              type: typeString ? NODE_TYPE_MAP[typeString as keyof typeof NODE_TYPE_MAP] : undefined,
            };
            this.activeService().addNode(node);
          }
          if (data.edges && Array.isArray(data.edges)) {
            for (const edgeData of data.edges) {
              this.activeService().addEdge(edgeData);
            }
          }
          resolve();
        } catch (error) {
          console.log("import error:", error)
          reject(error);
        }
      };
      input.click();
    });
  }
}
