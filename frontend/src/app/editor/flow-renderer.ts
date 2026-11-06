import { isSignal, untracked, WritableSignal } from '@angular/core';
import { createEdge, createNode, Edge, Node, StaticEdge, StaticNode } from 'ngx-vflow';

interface RenderedEntry<Input, Model> {
  input: Input;
  model: Model;
}

function isWritable(value: unknown): value is WritableSignal<unknown> {
  return isSignal(value) && typeof (value as WritableSignal<unknown>).set === 'function';
}

/** Keep serializable editor state separate from the renderer's mutable signals. */
export class FlowRenderer {
  private readonly nodeCache = new Map<string, RenderedEntry<StaticNode<any>, Node<any>>>();
  private readonly edgeCache = new Map<string, RenderedEntry<StaticEdge<any>, Edge<any>>>();

  nodes(inputs: StaticNode<any>[]): Node<any>[] {
    return untracked(() => this.reconcile(inputs, this.nodeCache, createNode));
  }

  edges(inputs: StaticEdge<any>[]): Edge<any>[] {
    return untracked(() => this.reconcile(inputs, this.edgeCache, createEdge));
  }

  private reconcile<Input extends { id: string; type?: unknown }, Model extends { id: string }>(
    inputs: Input[],
    cache: Map<string, RenderedEntry<Input, Model>>,
    create: (input: Input) => Model,
  ): Model[] {
    const liveIds = new Set(inputs.map(input => input.id));
    for (const id of cache.keys()) {
      if (!liveIds.has(id)) cache.delete(id);
    }

    return inputs.map(input => {
      const entry = cache.get(input.id);
      if (!entry || entry.input.type !== input.type) {
        const model = create(input);
        cache.set(input.id, { input, model });
        return model;
      }

      if (entry.input !== input) {
        const previousInput = entry.input as Record<string, unknown>;
        const nextInput = input as Record<string, unknown>;
        const model = entry.model as Record<string, unknown>;
        const nextModel = create(input) as Record<string, unknown>;

        for (const key of new Set([...Object.keys(previousInput), ...Object.keys(nextInput)])) {
          if (previousInput[key] === nextInput[key]) continue;
          const current = model[key];
          const next = nextModel[key];
          if (isWritable(current) && isSignal(next)) {
            current.set(next());
          } else {
            model[key] = next;
          }
        }
        entry.input = input;
      }

      return entry.model;
    });
  }
}
