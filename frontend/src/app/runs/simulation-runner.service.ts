import { Injectable, inject } from '@angular/core';
import { MessageService } from 'primeng/api';
import { GraphApiService, SimulationRunResponse, SimulationRunResult } from '../api/graph-api.service';
import { Architecture } from '../domain/topology';
import { GraphValidatorService } from '../editor/graph-validator.service';
import { GraphWorkspace } from '../editor/graph-workspace.service';
import { FrameworkJobsService } from './framework-jobs.service';
import { ArchitectureRunConfig, SimulationRequest, toStartRequest } from './simulation-request';

const RUN_STATUS_POLL_MS = 2000;
/** Consecutive status request failures tolerated before a run is reported as lost. */
const MAX_FAILED_STATUS_POLLS = 5;
const MAX_LISTED_VALIDATION_ERRORS = 5;

/** Validates, starts and follows simulations, reporting progress as jobs and toasts. */
@Injectable({ providedIn: 'root' })
export class SimulationRunner {
  private readonly api = inject(GraphApiService);
  private readonly validator = inject(GraphValidatorService);
  private readonly jobs = inject(FrameworkJobsService);
  private readonly messages = inject(MessageService);
  private readonly workspace = inject(GraphWorkspace);

  public async run(request: SimulationRequest): Promise<void> {
    if (request.mode === 'both') {
      await this.runCombined(request);
    } else {
      await this.runSingle(request.mode, request[request.mode]);
    }
  }

  private async runSingle(architecture: Architecture, config: ArchitectureRunConfig): Promise<void> {
    const graphId = await this.prepare(architecture, config);
    if (graphId === null) {
      return;
    }
    const jobId = this.jobs.startJob(`${architecture.toUpperCase()} simulation`);
    const runId = await this.start(jobId, `Failed to start ${architecture} simulation.`, () => {
      this.info(`${architecture} simulation queued with ${config.simulationSettings.repetitions} repetitions...`);
      return this.api.startSimulation(toStartRequest(graphId, config));
    });
    if (runId === null) {
      return;
    }
    const run = await this.followRun(runId, architecture, jobId);
    if (run) {
      this.success(formatSimulationResult(architecture, run));
    }
  }

  private async runCombined(request: SimulationRequest): Promise<void> {
    const hierflGraphId = await this.prepare('hierfl', request.hierfl);
    const spykerGraphId = await this.prepare('spyker', request.spyker);
    if (hierflGraphId === null || spykerGraphId === null) {
      return;
    }
    if (!sameSeeds(request.hierfl.simulationSettings.seedSet, request.spyker.simulationSettings.seedSet)) {
      this.error('Combined runs require identical seed sets for HierFL and Spyker.');
      return;
    }

    const jobId = this.jobs.startJob('SPYKER + HIERFL simulation');
    const runId = await this.start(jobId, 'Failed to start combined simulation.', () => {
      this.info(`Combined simulation queued with ${request.hierfl.simulationSettings.repetitions} repetitions...`);
      return this.api.startSimulationBoth({
        hierfl: toStartRequest(hierflGraphId, request.hierfl),
        spyker: toStartRequest(spykerGraphId, request.spyker),
      });
    });
    if (runId === null) {
      return;
    }
    const run = await this.followRun(runId, 'combined', jobId);
    const results = run?.results_by_architecture ?? {};
    for (const architecture of ['hierfl', 'spyker'] as const) {
      const result = results[architecture];
      if (result) {
        this.success(formatSimulationResult(architecture, result));
      }
    }
  }

  /** Saves and validates the graph. Returns its id, or null after reporting why it cannot run. */
  private async prepare(architecture: Architecture, config: ArchitectureRunConfig): Promise<number | null> {
    const graph = this.workspace.graphFor(architecture);
    const graphId = graph.getGraphId() ?? graph.loadGraphIdFromStorage();
    if (graphId === null) {
      this.error(`No graph available for ${architecture}. Please check if the backend is running.`);
      return null;
    }
    const errors = this.validator.validateSimulationRequest(architecture, graph.nodes(), graph.edges(), config);
    if (errors.length > 0) {
      this.showValidationErrors(architecture, errors);
      return null;
    }
    // The backend simulates the stored graph, so recent edits must be saved first.
    await graph.flushSave();
    return graphId;
  }

  private async start(
    jobId: string,
    failureMessage: string,
    request: () => Promise<SimulationRunResponse>,
  ): Promise<string | null> {
    try {
      return (await request()).run_id;
    } catch {
      this.error(failureMessage);
      this.jobs.markFailed(jobId);
      return null;
    }
  }

  /** Polls a run, mirroring its state into the job list. Resolves with the run once it completed. */
  private async followRun(runId: string, label: string, jobId: string): Promise<SimulationRunResponse | null> {
    let failedPolls = 0;
    for (;;) {
      let run: SimulationRunResponse;
      try {
        run = await this.api.getRunStatus(runId);
        failedPolls = 0;
      } catch {
        failedPolls += 1;
        if (failedPolls >= MAX_FAILED_STATUS_POLLS) {
          this.jobs.markFailed(jobId);
          this.error(`Lost track of the ${label} run ${runId}. Check the dashboard for its status.`);
          return null;
        }
        await sleep(RUN_STATUS_POLL_MS);
        continue;
      }
      switch (run.status) {
        case 'running':
          this.jobs.markRunning(jobId);
          break;
        case 'completed':
          this.jobs.markCompleted(jobId);
          return run;
        case 'failed':
          this.jobs.markFailed(jobId);
          this.error(`${label} simulation failed${run.error ? ` (${run.error})` : ''}`);
          return null;
      }
      await sleep(RUN_STATUS_POLL_MS);
    }
  }

  private showValidationErrors(architecture: Architecture, errors: string[]): void {
    const listed = errors.slice(0, MAX_LISTED_VALIDATION_ERRORS).map((error) => `- ${error}`).join('\n');
    const hidden = errors.length - MAX_LISTED_VALIDATION_ERRORS;
    this.messages.add({
      severity: 'error',
      summary: `${architecture} validation failed`,
      detail: hidden > 0 ? `${listed}\n...and ${hidden} more` : listed,
      life: 8000,
    });
  }

  private success(detail: string): void {
    this.messages.add({ severity: 'success', summary: 'Simulation completed', detail });
  }

  private info(detail: string): void {
    this.messages.add({ severity: 'info', summary: 'Simulation running', detail });
  }

  private error(detail: string): void {
    this.messages.add({ severity: 'error', summary: 'Error', detail });
  }
}

export function formatSimulationResult(architecture: Architecture, result: SimulationRunResult): string {
  const repetitions = result.repetitions ?? 1;
  const parts = [
    repetitions > 1
      ? `${repetitions} repetitions completed`
      : result.output_filename ? `Saved to ${result.output_filename}` : 'Completed',
  ];
  const summary = result.evaluation_summary;
  if (summary) {
    parts.push(
      `Mean accuracy ${(summary.mean_accuracy * 100).toFixed(2)}%`,
      `Accuracy variance ${summary.variance_accuracy.toFixed(6)}`,
      `Mean loss ${summary.mean_avg_loss.toFixed(4)}`,
      `Loss variance ${summary.variance_avg_loss.toFixed(6)}`,
    );
  } else if (result.evaluation) {
    parts.push(
      `Accuracy ${(result.evaluation.accuracy * 100).toFixed(2)}%`,
      `Loss ${result.evaluation.avg_loss.toFixed(4)}`,
    );
  }
  return `${architecture}: ${parts.join(', ')}`;
}

function sameSeeds(first: number[], second: number[]): boolean {
  return first.length === second.length && first.every((seed, index) => seed === second[index]);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
