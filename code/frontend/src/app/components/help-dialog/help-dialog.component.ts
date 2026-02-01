import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DialogModule } from 'primeng/dialog';
import { ButtonModule } from 'primeng/button';

@Component({
  selector: 'app-help-dialog',
  standalone: true,
  templateUrl: './help-dialog.component.html',
  styleUrls: ['./help-dialog.component.css'],
  imports: [CommonModule, DialogModule, ButtonModule],
})
export class HelpDialog {
  public visible = true;

  @Output() close = new EventEmitter<void>();

  public onClose(): void {
    this.visible = false;
    this.close.emit();
  }
}
