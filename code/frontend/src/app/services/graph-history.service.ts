import { Injectable, WritableSignal, signal } from '@angular/core';
import { Node, Edge } from 'ngx-vflow';

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
    this.redoStack.update((redoStack) => [...redoStack, oldState]);
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
    this.undoStack.update((undoStack) => [...undoStack, oldState]);
  }

  public saveState(newState: State) {
    const oldState = this.state();
    this.undoStack.update((undoStack) => [...undoStack, oldState])
    this.state.set(newState);
  }

  public resetHistory(newState: State) {
    this.state.set(newState);
    this.undoStack.set([]);
    this.redoStack.set([]);
  }
}
