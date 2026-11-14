import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';

export interface GraphState {
  nodes: Node[];
  edges: Edge[];
}

/** Undo steps kept per graph; older ones are dropped. */
export const HISTORY_LIMIT = 100;

/**
 * Undo/redo over committed graph states. States are immutable snapshots and
 * stored by reference; selection flags are stripped because they are view state.
 */
export class GraphHistory {
  private present: GraphState = { nodes: [], edges: [] };
  private past: GraphState[] = [];
  private future: GraphState[] = [];

  constructor(private readonly limit = HISTORY_LIMIT) {}

  public getState(): GraphState {
    return this.present;
  }

  public saveState(state: GraphState): void {
    this.past.push(this.present);
    if (this.past.length > this.limit) {
      this.past.shift();
    }
    this.future = [];
    this.present = withoutSelection(state);
  }

  public resetHistory(state: GraphState): void {
    this.past = [];
    this.future = [];
    this.present = withoutSelection(state);
  }

  public undo(): void {
    const previous = this.past.pop();
    if (previous) {
      this.future.push(this.present);
      this.present = previous;
    }
  }

  public redo(): void {
    const next = this.future.pop();
    if (next) {
      this.past.push(this.present);
      this.present = next;
    }
  }
}

function withoutSelection(state: GraphState): GraphState {
  return { nodes: state.nodes.map(unselected), edges: state.edges.map(unselected) };
}

function unselected<T>(item: T): T {
  const data = (item as { data?: { selected?: boolean } }).data;
  return data?.selected ? { ...item, data: { ...data, selected: false } } : item;
}
