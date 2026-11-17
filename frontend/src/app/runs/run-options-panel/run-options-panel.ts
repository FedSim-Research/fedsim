import { Component, EventEmitter, Input, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { InputNumberModule } from 'primeng/inputnumber';
import { RunOption, RunOptionSection, RunOptionValue, RunOptionValues } from '../run-options';

/** Renders declarative run options generically, so new controls need no template changes. */
@Component({
  selector: 'app-run-options-panel',
  standalone: true,
  imports: [CommonModule, FormsModule, InputNumberModule],
  templateUrl: './run-options-panel.html',
})
export class RunOptionsPanel {
  @Input({ required: true }) options: readonly RunOption[] = [];
  @Input({ required: true }) values: RunOptionValues = {};
  @Input() section: RunOptionSection | null = null;
  @Output() valuesChange = new EventEmitter<RunOptionValues>();

  get visibleOptions(): readonly RunOption[] {
    return this.section ? this.options.filter((o) => o.section === this.section) : this.options;
  }

  update(key: string, value: RunOptionValue | undefined): void {
    this.values[key] = value === undefined ? null : value;
    this.valuesChange.emit(this.values);
  }
}
