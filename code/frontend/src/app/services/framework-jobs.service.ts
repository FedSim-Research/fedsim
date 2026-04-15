import { Injectable, computed, signal } from '@angular/core';
import { v4 as uuidv4 } from 'uuid';

export type FrameworkJobStatus = 'queued' | 'running' | 'completed' | 'failed';

export interface FrameworkJob {
  id: string;
  title: string;
  status: FrameworkJobStatus;
  startedAt: number;
  completedAt?: number;
}

@Injectable({ providedIn: 'root' })
export class FrameworkJobsService {
  private jobsState = signal<FrameworkJob[]>([]);
  public jobs = this.jobsState.asReadonly();
  public runningCount = computed(
    () => this.jobsState().filter((job) => job.status === 'queued' || job.status === 'running').length
  );

  public startJob(title: string): string {
    const id = uuidv4();
    const next: FrameworkJob = {
      id,
      title,
      status: 'queued',
      startedAt: Date.now(),
    };
    this.jobsState.update((jobs) => [next, ...jobs]);
    return id;
  }

  public markRunning(id: string): void {
    this.jobsState.update((jobs) =>
      jobs.map((job) =>
        job.id === id
          ? {
              ...job,
              status: 'running',
            }
          : job
      )
    );
  }

  public markCompleted(id: string): void {
    this.jobsState.update((jobs) =>
      jobs.map((job) =>
        job.id === id
          ? {
              ...job,
              status: 'completed',
              completedAt: Date.now(),
            }
          : job
      )
    );
  }

  public markFailed(id: string): void {
    this.jobsState.update((jobs) =>
      jobs.map((job) =>
        job.id === id
          ? {
              ...job,
              status: 'failed',
              completedAt: Date.now(),
            }
          : job
      )
    );
  }
}
