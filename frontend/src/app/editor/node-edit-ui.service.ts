import { Injectable, signal } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class NodeEditUiService {
  private editingNodeId = signal<string | null>(null);
  private drafts = signal<Record<string, Record<string, unknown>>>({});

  public activeId = this.editingNodeId.asReadonly();

  public startEditing(nodeId: string, initialDraft: Record<string, unknown>): void {
    this.editingNodeId.set(nodeId);
    this.drafts.update((current) => ({ ...current, [nodeId]: initialDraft }));
  }

  public stopEditing(nodeId: string): void {
    if (this.editingNodeId() === nodeId) {
      this.editingNodeId.set(null);
    }
  }

  public updateDraft(nodeId: string, patch: Record<string, unknown>): void {
    this.drafts.update((current) => ({
      ...current,
      [nodeId]: {
        ...(current[nodeId] ?? {}),
        ...patch,
      },
    }));
  }

  public getDraft<T extends Record<string, unknown>>(nodeId: string, fallback: T): T {
    const draft = this.drafts()[nodeId] ?? {};
    return { ...fallback, ...draft } as T;
  }

  public clearDraft(nodeId: string): void {
    this.drafts.update((current) => {
      const { [nodeId]: _removed, ...rest } = current;
      return rest;
    });
  }
}
