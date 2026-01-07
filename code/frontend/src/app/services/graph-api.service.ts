import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { firstValueFrom } from 'rxjs';

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
  node_id: number;
  graph_id: number;
  external_id: string;
  type: string;
  config: Record<string, unknown>;
  position: Position;
}

export interface EdgeResponse {
  edge_id: number;
  graph_id: number;
  source_node_id: number;
  target_node_id: number;
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


export interface NodeCreate {
  external_id?: string | null;
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
  source_node_id?: number | null;
  target_node_id?: number | null;
  source_external_id?: string | null;
  target_external_id?: string | null;
}

@Injectable({ providedIn: 'root' })
export class GraphApiService {
  private http = inject(HttpClient);
  private baseUrl = (window as any).FEDSIM_API_BASE_URL ?? 'http://localhost:8000';

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

  public async createNode(graphId: number, payload: NodeCreate): Promise<NodeResponse> {
    return firstValueFrom(this.http.post<NodeResponse>(this.url(`/graphs/${graphId}/nodes`), payload));
  }

  public async updateNode(nodeId: number, payload: NodeUpdate): Promise<NodeResponse> {
    return firstValueFrom(this.http.put<NodeResponse>(this.url(`/nodes/${nodeId}`), payload));
  }

  public async deleteNode(nodeId: number): Promise<void> {
    await firstValueFrom(this.http.delete(this.url(`/nodes/${nodeId}`)));
  }

  public async createEdge(graphId: number, payload: EdgeCreate): Promise<EdgeResponse> {
    return firstValueFrom(this.http.post<EdgeResponse>(this.url(`/graphs/${graphId}/edges`), payload));
  }

  public async deleteEdge(edgeId: number): Promise<void> {
    await firstValueFrom(this.http.delete(this.url(`/edges/${edgeId}`)));
  }
}
