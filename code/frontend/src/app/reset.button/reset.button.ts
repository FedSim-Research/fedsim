import { Component, EventEmitter, Output } from '@angular/core';

@Component({
  selector: 'app-reset-button', 
  standalone: true,
  imports: [],
  templateUrl: './reset.button.html',
  styleUrl: './reset.button.css',
})
export class ResetButton {
  @Output() reset = new EventEmitter<void>();

  public onClick() {
    this.reset.emit();
  }
}