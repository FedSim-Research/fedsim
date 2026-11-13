import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { normalizeEdgeMetrics } from '../api/edge-metrics';

export const GRAPH_FILE_VERSION = 1;

export interface GraphFileNode {
  id: string;
  point: { x: number; y: number };
  data: { type: string; config: Record<string, unknown> };
}

export interface GraphFileEdge {
  id: string;
  source: string;
  target: string;
  sourceHandle: string | null;
  targetHandle: string | null;
  data: { metrics: ReturnType<typeof normalizeEdgeMetrics> };
}

/**
 * Portable graph export. Contains only the topology and its configuration,
 * never backend ids or view state, so a file can be imported into any graph.
 */
export interface GraphFile {
  version: typeof GRAPH_FILE_VERSION;
  architecture: 'spyker' | 'hierfl';
  nodes: GraphFileNode[];
  edges: GraphFileEdge[];
  nodeCount: number;
  edgeCount: number;
}

export function toGraphFile(
  architecture: 'spyker' | 'hierfl',
  nodes: Node[],
  edges: Edge[],
): GraphFile {
  const fileNodes = nodes.map((node): GraphFileNode => {
    const data = (node as { data?: { type?: unknown; config?: unknown } }).data ?? {};
    return {
      id: node.id,
      point: { x: node.point?.x ?? 0, y: node.point?.y ?? 0 },
      data: {
        type: String(data.type ?? ''),
        config: { ...((data.config as Record<string, unknown> | undefined) ?? {}) },
      },
    };
  });
  const fileEdges = edges.map((edge): GraphFileEdge => {
    const data = (edge as { data?: { metrics?: Record<string, unknown> } }).data;
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
      data: { metrics: normalizeEdgeMetrics(data?.metrics) },
    };
  });
  return {
    version: GRAPH_FILE_VERSION,
    architecture,
    nodes: fileNodes,
    edges: fileEdges,
    nodeCount: fileNodes.length,
    edgeCount: fileEdges.length,
  };
}
