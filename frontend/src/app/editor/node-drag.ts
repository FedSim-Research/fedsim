import { NodePositionChange } from 'ngx-vflow';
import { ArchitectureGraph } from './graph-workspace.service';

type Point = { x: number; y: number };

/** Ignores the position echo the canvas emits right after a drag was committed. */
const COOLDOWN_MS = 50;
const END_EVENTS = ['pointerup', 'pointercancel', 'mouseup', 'touchend', 'touchcancel'];

/**
 * Turns the canvas' position events into one committed move per drag. Selected
 * nodes follow the dragged one; all positions are derived from where the drag started.
 */
export class NodeDrag {
  private origin: Map<string, Point> | null = null;
  private draggedId: string | null = null;
  private pending: NodePositionChange[] | null = null;
  private ignoreUntil = 0;
  private endListeners: AbortController | null = null;

  constructor(
    private readonly graph: () => ArchitectureGraph,
    private readonly selection: () => ReadonlySet<string>,
  ) {}

  public handle(changes: NodePositionChange[]): void {
    if (!changes.length || Date.now() < this.ignoreUntil) {
      return;
    }
    if (!this.origin) {
      this.begin(changes[0].id);
    }
    const moved = this.withFollowers(changes);
    // The canvas already shows the dragged node where it is; only followers need a preview.
    this.graph().previewPositions(moved.filter((change) => change.id !== this.draggedId));
    this.pending = moved;
  }

  /** Commits the drag. Called by the first pointer/touch end event. */
  public finish(): void {
    this.endListeners?.abort();
    this.endListeners = null;
    this.origin = null;
    this.draggedId = null;
    this.ignoreUntil = Date.now() + COOLDOWN_MS;
    if (this.pending) {
      this.graph().moveNodes(this.pending);
      this.pending = null;
    }
  }

  private begin(draggedId: string): void {
    this.draggedId = draggedId;
    this.origin = new Map(this.graph().nodes().map((node) => [node.id, { x: node.point.x, y: node.point.y }]));
    this.endListeners = new AbortController();
    for (const type of END_EVENTS) {
      window.addEventListener(type, () => this.finish(), { signal: this.endListeners.signal });
    }
  }

  private withFollowers(changes: NodePositionChange[]): NodePositionChange[] {
    const selection = this.selection();
    const lead = changes[0];
    const start = this.origin?.get(lead.id);
    if (!start || selection.size <= 1 || !selection.has(lead.id)) {
      return changes;
    }
    const dx = lead.point.x - start.x;
    const dy = lead.point.y - start.y;
    const changed = new Set(changes.map((change) => change.id));
    const followers: NodePositionChange[] = [];
    for (const id of selection) {
      const from = this.origin?.get(id);
      if (from && !changed.has(id)) {
        followers.push({ type: 'position', id, point: { x: from.x + dx, y: from.y + dy } });
      }
    }
    return [...changes, ...followers];
  }
}
