import { Injectable, WritableSignal, signal } from '@angular/core';
import { StaticNode as Node, StaticEdge as Edge } from 'ngx-vflow';

export interface State{
  nodes: Node[];
  edges: Edge[];
}

@Injectable({
  providedIn: 'root',
})
export abstract class GraphHistoryService {
  private state = signal<State>({nodes: [], edges: []});
  private undoStack = signal<State[]>([]);
  private redoStack = signal<State[]>([]);

  public getNodes() {
    return this.state().nodes;
  }

  public getEdges() {
    return this.state().edges;
  }

  public getState() {
    return this.state();
  }

  public undo() {
    if (this.undoStack().length <= 0){
      return;
    }
    const oldState = this.state();
    const stack = this.undoStack();
    let newState = stack[stack.length-1];
    this.state.set(newState);
    stack.pop();
    this.undoStack.update((undoStack) => stack);
    this.redoStack.update((redoStack) => [...redoStack, this.sanitizeState(oldState)]);
  }

  public redo() {
    if (this.redoStack().length <= 0){
      return;
    }
    const oldState = this.state();
    const stack = this.redoStack();
    let newState = stack[stack.length-1];
    this.state.set(newState);
    stack.pop();
    this.redoStack.update(() => stack);
    this.undoStack.update((undoStack) => [...undoStack, this.sanitizeState(oldState)]);
  }

  public saveState(newState: State) {
    const oldState = this.state();
    this.undoStack.update((undoStack) => [...undoStack, this.sanitizeState(oldState)]);
    this.redoStack.set([]);
    this.state.set(this.sanitizeState(newState));
  }

  public replaceCurrentState(newState: State): void {
    this.state.set(this.sanitizeState(newState));
  }

  public resetHistory(newState: State) {
    this.state.set(this.sanitizeState(newState));
    this.undoStack.set([]);
    this.redoStack.set([]);
  }

  private sanitizeState(state: State): State {
    return {
      nodes: state.nodes.map((node) => {
        const data = ((node as any).data as Record<string, unknown> | undefined) ?? undefined;
        const config = data?.['config'];
        return {
          ...node,
          point: node.point ? { ...node.point } : node.point,
          data: data
            ? {
                ...data,
                config: config && typeof config === 'object' ? { ...(config as Record<string, unknown>) } : config,
                selected: false,
              }
            : data,
        } as Node;
      }),
      edges: state.edges.map((edge) => {
        const data = ((edge as any).data as Record<string, unknown> | undefined) ?? undefined;
        const metrics = data?.['metrics'];
        return {
          ...edge,
          data: data
            ? {
                ...data,
                metrics: metrics && typeof metrics === 'object'
                  ? { ...(metrics as Record<string, unknown>) }
                  : metrics,
                selected: false,
              }
            : data,
        } as Edge;
      }),
    };
  }
}
