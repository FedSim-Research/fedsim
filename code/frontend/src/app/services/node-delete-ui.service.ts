import { Injectable, signal } from '@angular/core';
import { Subject } from 'rxjs';

@Injectable({ providedIn: 'root' })
export class NodeDeleteUiService {
  private activeNodeId = signal<string | null>(null);
  private deleteRequests = new Subject<string>();

  public activeId = this.activeNodeId.asReadonly();
  public deleteRequests$ = this.deleteRequests.asObservable();

  public showFor(nodeId: string): void {
    if (this.activeNodeId() === nodeId) {
      this.activeNodeId.set(null);
      return;
    }
    this.activeNodeId.set(nodeId);
  }

  public requestDelete(nodeId: string): void {
    this.deleteRequests.next(nodeId);
    this.activeNodeId.set(null);
  }
}
