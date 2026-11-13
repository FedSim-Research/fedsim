import { Injectable } from '@angular/core';
import { Subject } from 'rxjs';

export type ForwardKind = 'client' | 'server' | 'superserver';

export interface NodeForward {
  kind: ForwardKind;
  config: Record<string, unknown>;
}

/** Requests canvas nodes raise for the rest of the editor. */
@Injectable({ providedIn: 'root' })
export class NodeEvents {
  private readonly selectionToggles = new Subject<string>();
  private readonly forwards = new Subject<NodeForward>();

  /** Node ids whose selection should flip (ctrl/cmd + click). */
  public readonly selectionToggled$ = this.selectionToggles.asObservable();
  /** Node settings to copy into the sidebar. */
  public readonly forwarded$ = this.forwards.asObservable();

  public toggleSelection(nodeId: string): void {
    this.selectionToggles.next(nodeId);
  }

  public forward(forward: NodeForward): void {
    this.forwards.next(forward);
  }
}
