import { CommonModule } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';
import { FrameworkJobsService } from '../../services/framework-jobs.service';

@Component({
  selector: 'app-framework-jobs-popup',
  standalone: true,
  imports: [CommonModule],
  templateUrl: './framework-jobs-popup.component.html',
  styleUrl: './framework-jobs-popup.component.css',
})
export class FrameworkJobsPopupComponent {
  private jobsService = inject(FrameworkJobsService);
  public isOpen = signal(false);
  public jobs = this.jobsService.jobs;
  public runningCount = this.jobsService.runningCount;
  public completedCount = computed(
    () => this.jobs().filter((job) => job.status === 'completed').length
  );

  public toggle(): void {
    this.isOpen.update((value) => !value);
  }
}
