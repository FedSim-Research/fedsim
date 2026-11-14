import { NodePositionChange } from 'ngx-vflow';
import { ArchitectureGraph } from './graph-workspace.service';

type Point = { x: number; y: number };

/**
 * The canvas derives position events from signal changes and delivers them after
 * change detection, so the last ones can arrive after the pointer was released.
 */
const SETTLE_MS = 50;

/**
 * Turns the canvas' position events into one committed move per drag. Selected
 * nodes follow the dragged one; all positions are derived from where the drag started.
 *
 * The canvas also reports position changes the app makes itself (follower previews,
 * undo, committed moves). A drag therefore only starts while a pointer is held down,
 * and only events for the grabbed node move it.
 */
export class NodeDrag {
  private pointerDown = false;
  private origin: Map<string, Point> | null = null;
  private draggedId: string | null = null;
  private pending: NodePositionChange[] | null = null;
  private settling = false;
  private settleTimer: ReturnType<typeof setTimeout> | null = null;
  private activeGraph: ArchitectureGraph | null = null;
  private graphId: number | null = null;
  private selectedIds: ReadonlySet<string> = new Set();
  private readonly listeners = new AbortController();

  constructor(
    private readonly graph: () => ArchitectureGraph,
    private readonly selection: () => ReadonlySet<string>,
    target: Pick<Window, 'addEventListener'> = window,
  ) {
    const options = { capture: true, signal: this.listeners.signal };
    target.addEventListener('pointerdown', () => {
      if (this.settling) this.commit();
      this.pointerDown = true;
    }, options);
    for (const type of ['pointerup', 'pointercancel']) {
      target.addEventListener(type, () => this.finish(), options);
    }
  }

  public handle(changes: NodePositionChange[]): void {
    if (!changes.length) {
      return;
    }
    if (this.activeGraph && (this.activeGraph !== this.graph() || this.activeGraph.getGraphId() !== this.graphId)) {
      this.commit();
      this.pointerDown = false;
      return;
    }
    if (!this.origin) {
      if (!this.pointerDown) {
        return;
      }
      this.begin(changes[0].id);
    }
    const lead = changes.find((change) => change.id === this.draggedId);
    if (!lead) {
      return;
    }
    const moved = this.withFollowers(lead);
    // The canvas already shows the dragged node where it is; only followers need a preview.
    this.activeGraph?.previewPositions(moved.filter((change) => change.id !== this.draggedId));
    this.pending = moved;
  }

  /** Stops listening for pointer events. */
  public destroy(): void {
    this.listeners.abort();
    this.commit();
    this.pointerDown = false;
  }

  private begin(draggedId: string): void {
    this.activeGraph = this.graph();
    this.graphId = this.activeGraph.getGraphId();
    this.selectedIds = new Set(this.selection());
    this.draggedId = draggedId;
    this.origin = new Map(this.graph().nodes().map((node) => [node.id, { x: node.point.x, y: node.point.y }]));
  }

  /** Ends the pointer gesture; the drag is committed once trailing events arrived. */
  private finish(): void {
    this.pointerDown = false;
    if (this.origin && !this.settling) {
      this.settling = true;
      this.settleTimer = setTimeout(() => this.commit(), SETTLE_MS);
    }
  }

  private commit(): void {
    if (this.settleTimer !== null) clearTimeout(this.settleTimer);
    this.settleTimer = null;
    const pending = this.pending;
    const graph = this.activeGraph;
    const graphId = this.graphId;
    this.origin = null;
    this.draggedId = null;
    this.pending = null;
    this.settling = false;
    this.activeGraph = null;
    if (pending && graph && graph.getGraphId() === graphId) {
      graph.moveNodes(pending);
    }
  }

  private withFollowers(lead: NodePositionChange): NodePositionChange[] {
    const selection = this.selectedIds;
    const start = this.origin?.get(lead.id);
    if (!start || selection.size <= 1 || !selection.has(lead.id)) {
      return [lead];
    }
    const dx = lead.point.x - start.x;
    const dy = lead.point.y - start.y;
    const followers: NodePositionChange[] = [];
    for (const id of selection) {
      const from = this.origin?.get(id);
      if (from && id !== lead.id) {
        followers.push({ type: 'position', id, point: { x: from.x + dx, y: from.y + dy } });
      }
    }
    return [lead, ...followers];
  }
}
