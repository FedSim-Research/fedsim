import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';
import { environment } from '../../environments/environment';
import { EdgeMetrics } from '../models/edge-metrics';

export interface Position {
  x: number;
  y: number;
}

export interface GraphResponse {
  graph_id: number;
  name: string | null;
  architecture: 'spyker' | 'hierfl';
  metadata: Record<string, unknown> | null;
}

export interface NodeResponse {
  node_id: string;
  graph_id: number;
  type: string;
  config: Record<string, unknown>;
  position: Position;
}

export interface EdgeResponse {
  edge_id: number;
  graph_id: number;
  source_node_id: string;
  target_node_id: string;
  config: EdgeMetrics;
}

export interface GraphDetail extends GraphResponse {
  nodes: NodeResponse[];
  edges: EdgeResponse[];
}

export interface GraphCreate {
  name?: string | null;
  architecture: 'spyker' | 'hierfl';
  metadata?: Record<string, unknown> | null;
}

export interface GraphRename {
  name: string;
}

export interface GraphMetadataPatch {
  patch: Record<string, unknown>;
}


export interface NodeCreate {
  type: 'ClientNode' | 'ServerNode' | 'SuperServerNode';
  config: Record<string, unknown>;
  position: Position;
}

export interface NodeUpdate {
  type?: 'ClientNode' | 'ServerNode' | 'SuperServerNode';
  config?: Record<string, unknown>;
  position?: Position;
}

export interface EdgeCreate {
  source_node_id?: string | null;
  target_node_id?: string | null;
  config?: EdgeMetrics | null;
}

export interface EdgeUpdate {
  config: EdgeMetrics;
}

export interface VflowNodeData {
  type: 'ClientNode' | 'ServerNode' | 'SuperServerNode';
  config: Record<string, unknown>;
  environment?: string | null;
  fromJson?: boolean;
  selected?: boolean;
}

export interface VflowNode {
  id: string;
  point: Position;
  type: string;
  data: VflowNodeData;
}

export interface VflowEdge {
  id: string;
  source: string;
  target: string;
  config?: EdgeMetrics | null;
  sourceHandle?: string | null;
  targetHandle?: string | null;
  reconnectable?: boolean | 'source' | 'target';
  floating?: boolean;
}

export interface VflowGraph {
  nodes: VflowNode[];
  edges: VflowEdge[];
}

export interface SimulationStartRequest {
  graph_id: number;
  training_config?: {
    epochs: number;
    lr: number;
    model_complexity?: number;
    batch_size?: number;
  };
  simulation_settings?: {
    run_time_limit?: number;
    eval_interval?: number;
    idle_token_delay?: number;
    gpu_budget?: number;
    dataset?: string;
    seed?: number;
    seed_set?: number[];
    repetitions?: number;
    output_filename?: string | null;
    evaluate_model?: boolean;
  };
  spyker_config?: {
    decay_beta?: number;
    min_learning_rate?: number;
    h_inter?: number;
    h_intra?: number;
    sigmoid_phi?: number;
    server_learning_rate?: number;
    tcp_rto_delay?: number;
  };
}

export interface SimulationStartBothRequest {
  hierfl: SimulationStartRequest;
  spyker: SimulationStartRequest;
}

export interface SimulationRunResult {
  architecture?: 'spyker' | 'hierfl' | string;
  graph_id?: number | null;
  seed?: number | null;
  seed_set?: number[] | null;
  repetitions?: number | null;
  completed_repetitions?: number | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  output_filename?: string | null;
  evaluation?: {
    accuracy: number;
    avg_loss: number;
  } | null;
  evaluation_summary?: {
    evaluated_repetitions: number;
    mean_accuracy: number;
    variance_accuracy: number;
    mean_avg_loss: number;
    variance_avg_loss: number;
  } | null;
  runs?: Array<{
    seed: number;
    repetition_index: number;
    duration_seconds?: number | null;
    output_filename?: string | null;
    evaluation?: {
      accuracy: number;
      avg_loss: number;
    } | null;
  }> | null;
  results_by_architecture?: Record<
    string,
    {
      seed?: number | null;
      seed_set?: number[] | null;
      repetitions?: number | null;
      completed_repetitions?: number | null;
      output_filename?: string | null;
      evaluation?: {
        accuracy: number;
        avg_loss: number;
      } | null;
      evaluation_summary?: {
        evaluated_repetitions: number;
        mean_accuracy: number;
        variance_accuracy: number;
        mean_avg_loss: number;
        variance_avg_loss: number;
      } | null;
      runs?: Array<{
        seed: number;
        repetition_index: number;
        duration_seconds?: number | null;
        output_filename?: string | null;
        evaluation?: {
          accuracy: number;
          avg_loss: number;
        } | null;
      }> | null;
    }
  > | null;
}

export interface SimulationRunResponse {
  run_id: string;
  status: 'queued' | 'running' | 'completed' | 'failed';
  architecture?: 'spyker' | 'hierfl' | 'both';
  graph_id?: number | null;
  seed?: number | null;
  queued_at?: string | null;
  started_at?: string | null;
  finished_at?: string | null;
  duration_seconds?: number | null;
  current_sim_time?: number | null;
  run_time_limit?: number | null;
  output_filename?: string | null;
  dataset?: string | null;
  datasets_by_architecture?: Record<string, string | null> | null;
  accuracy_loss_snapshot_url?: string | null;
  accuracy_loss_snapshot_urls_by_architecture?: Record<string, string | null> | null;
  seed_set?: number[] | null;
  repetitions?: number | null;
  completed_repetitions?: number | null;
  error?: string | null;
  evaluation?: {
    accuracy: number;
    avg_loss: number;
  } | null;
  evaluation_summary?: {
    evaluated_repetitions: number;
    mean_accuracy: number;
    variance_accuracy: number;
    mean_avg_loss: number;
    variance_avg_loss: number;
  } | null;
  runs?: Array<{
    seed: number;
    repetition_index: number;
    duration_seconds?: number | null;
    output_filename?: string | null;
    evaluation?: {
      accuracy: number;
      avg_loss: number;
    } | null;
  }> | null;
  results_by_architecture?: Record<string, SimulationRunResult> | null;
  run_metadata?: Record<string, unknown> | null;
  final_run_summary?: Record<string, unknown> | null;
}

export interface PresetResponse {
  preset_id: number;
  architecture: 'spyker' | 'hierfl';
  node_type: 'SuperServerNode' | 'ServerNode' | 'ClientNode';
  name: string;
  config: Record<string, unknown>;
}

export interface PresetCreate {
  architecture: 'spyker' | 'hierfl';
  node_type: 'SuperServerNode' | 'ServerNode' | 'ClientNode';
  name: string;
  config: Record<string, unknown>;
}

export interface PresetUpdate {
  name?: string;
  config?: Record<string, unknown>;
}

@Injectable({ providedIn: 'root' })
export class GraphApiService {
  private http = inject(HttpClient);
  private baseUrl = (window as any).FEDSIM_API_BASE_URL ?? environment.apiBaseUrl;

  private url(path: string): string {
    const trimmed = this.baseUrl.replace(/\/+$/, '');
    return `${trimmed}${path}`;
  }

  public async createGraph(payload: GraphCreate): Promise<GraphResponse> {
    return firstValueFrom(this.http.post<GraphResponse>(this.url('/graphs/'), payload));
  }

  public async listGraphs(): Promise<GraphResponse[]> {
    return firstValueFrom(this.http.get<GraphResponse[]>(this.url('/graphs/')));
  }

  public async getGraph(graphId: number): Promise<GraphDetail> {
    return firstValueFrom(this.http.get<GraphDetail>(this.url(`/graphs/${graphId}`)));
  }

  public async deleteGraph(graphId: number): Promise<void> {
    await firstValueFrom(this.http.delete(this.url(`/graphs/${graphId}`)));
  }

  public async renameGraph(graphId: number, payload: GraphRename): Promise<GraphResponse> {
    return firstValueFrom(this.http.put<GraphResponse>(this.url(`/graphs/${graphId}/name`), payload));
  }

  public async patchGraphMetadata(graphId: number, payload: GraphMetadataPatch): Promise<GraphResponse> {
    return firstValueFrom(this.http.patch<GraphResponse>(this.url(`/graphs/${graphId}/metadata`), payload));
  }

  public async createNode(graphId: number, payload: NodeCreate): Promise<NodeResponse> {
    return firstValueFrom(this.http.post<NodeResponse>(this.url(`/graphs/${graphId}/nodes`), payload));
  }

  public async updateNode(nodeId: string, payload: NodeUpdate): Promise<NodeResponse> {
    return firstValueFrom(this.http.put<NodeResponse>(this.url(`/nodes/${nodeId}`), payload));
  }

  public async deleteNode(nodeId: string): Promise<void> {
    await firstValueFrom(this.http.delete(this.url(`/nodes/${nodeId}`)));
  }

  public async createEdge(graphId: number, payload: EdgeCreate): Promise<EdgeResponse> {
    return firstValueFrom(this.http.post<EdgeResponse>(this.url(`/graphs/${graphId}/edges`), payload));
  }

  public async updateEdge(edgeId: number, payload: EdgeUpdate): Promise<EdgeResponse> {
    return firstValueFrom(this.http.put<EdgeResponse>(this.url(`/edges/${edgeId}`), payload));
  }

  public async deleteEdge(edgeId: number): Promise<void> {
    await firstValueFrom(this.http.delete(this.url(`/edges/${edgeId}`)));
  }

  public async startSimulation(payload: SimulationStartRequest): Promise<SimulationRunResponse> {
    return firstValueFrom(this.http.post<SimulationRunResponse>(this.url('/start_simulation'), payload));
  }

  public async startSimulationBoth(payload: SimulationStartBothRequest): Promise<SimulationRunResponse> {
    return firstValueFrom(this.http.post<SimulationRunResponse>(this.url('/start_simulation_both'), payload));
  }

  public async getRunStatus(runId: string): Promise<SimulationRunResponse> {
    return firstValueFrom(this.http.get<SimulationRunResponse>(this.url(`/runs/${runId}`)));
  }

  public async listRuns(): Promise<SimulationRunResponse[]> {
    return firstValueFrom(this.http.get<SimulationRunResponse[]>(this.url('/runs')));
  }

  public async deleteRun(runId: string): Promise<void> {
    await firstValueFrom(this.http.delete(this.url(`/runs/${runId}`)));
  }

  public async replaceGraphState(graphId: number, payload: VflowGraph): Promise<GraphDetail> {
    return firstValueFrom(this.http.put<GraphDetail>(this.url(`/graphs/${graphId}/state`), payload));
  }

  public async listPresets(
    architecture: 'spyker' | 'hierfl',
    nodeType: 'SuperServerNode' | 'ServerNode' | 'ClientNode'
  ): Promise<PresetResponse[]> {
    return firstValueFrom(
      this.http.get<PresetResponse[]>(
        this.url(`/presets/?architecture=${architecture}&node_type=${nodeType}`)
      )
    );
  }

  public async createPreset(payload: PresetCreate): Promise<PresetResponse> {
    return firstValueFrom(this.http.post<PresetResponse>(this.url('/presets/'), payload));
  }

  public async updatePreset(presetId: number, payload: PresetUpdate): Promise<PresetResponse> {
    return firstValueFrom(this.http.put<PresetResponse>(this.url(`/presets/${presetId}`), payload));
  }

  public async deletePreset(presetId: number): Promise<void> {
    await firstValueFrom(this.http.delete(this.url(`/presets/${presetId}`)));
  }
}
