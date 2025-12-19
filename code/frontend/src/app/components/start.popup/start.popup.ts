import { Component, EventEmitter, Output } from '@angular/core';
import { CommonModule } from '@angular/common';

@Component({
  selector: 'app-start-popup', 
  standalone: true,
  imports: [CommonModule],
  templateUrl: './start.popup.html',
  styleUrl: './start.popup.css',
})
export class StartPopup {
  @Output() close = new EventEmitter<void>();
  @Output() run = new EventEmitter<'spyker' | 'hierarchical' | 'both'>();

  public onClose() {
    this.close.emit();
  }

  public onRun(type: 'spyker' | 'hierarchical' | 'both') {
    this.run.emit(type);
  }
}