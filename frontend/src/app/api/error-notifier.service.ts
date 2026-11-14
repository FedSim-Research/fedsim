import { Injectable, inject } from '@angular/core';
import { MessageService } from 'primeng/api';

const DUPLICATE_WINDOW_MS = 3000;

/** Shows error toasts, collapsing identical messages raised within a short window. */
@Injectable({ providedIn: 'root' })
export class ErrorNotifier {
  private readonly messages = inject(MessageService);
  private readonly lastShown = new Map<string, number>();

  public error(summary: string, detail: string): void {
    const key = `${summary}\u0000${detail}`;
    const now = Date.now();
    const previous = this.lastShown.get(key);
    if (previous !== undefined && now - previous < DUPLICATE_WINDOW_MS) {
      return;
    }
    this.lastShown.set(key, now);
    this.messages.add({ severity: 'error', summary, detail });
  }
}
