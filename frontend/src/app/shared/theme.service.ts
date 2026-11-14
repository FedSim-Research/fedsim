import { DOCUMENT } from '@angular/common';
import { Injectable, inject, signal } from '@angular/core';

/** One theme selection for application styles, PrimeNG and embedded dashboards. */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  private readonly document = inject(DOCUMENT);
  private readonly dark = signal(!this.document.body.classList.contains('light-mode'));
  public readonly isDark = this.dark.asReadonly();

  public toggle(): void {
    this.dark.update((current) => !current);
    this.document.body.classList.toggle('light-mode', !this.dark());
  }
}
