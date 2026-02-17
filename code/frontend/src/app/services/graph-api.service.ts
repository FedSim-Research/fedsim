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
  };
  simulation_settings?: {
    run_time_limit?: number;
    output_filename?: string | null;
    evaluate_model?: boolean;
  };
}

export interface SimulationStartResponse {
  status: 'completed';
  graph_id: number;
  architecture: 'spyker' | 'hierfl';
  output_filename?: string | null;
  evaluation?: {
    accuracy: number;
    avg_loss: number;
  } | null;
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

  public async startSimulation(payload: SimulationStartRequest): Promise<SimulationStartResponse> {
    return firstValueFrom(this.http.post<SimulationStartResponse>(this.url('/start_simulation'), payload));
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
