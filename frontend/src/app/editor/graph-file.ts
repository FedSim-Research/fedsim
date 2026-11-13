import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { normalizeEdgeMetrics } from '../api/edge-metrics';
import { GraphDetail } from '../api/graph-api.service';

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

/** Builds an export straight from a stored graph, independent of what the canvas shows. */
export function graphFileFromDetail(detail: GraphDetail): GraphFile {
  const nodes = detail.nodes.map((node) => ({
    id: node.node_id,
    point: node.position,
    data: { type: node.type, config: node.config },
  }));
  const edges = detail.edges.map((edge) => ({
    id: String(edge.edge_id),
    source: edge.source_node_id,
    target: edge.target_node_id,
    data: { metrics: edge.config },
  }));
  return toGraphFile(detail.architecture, nodes as unknown as Node[], edges);
}

/** Lowercase, dash-separated name that is safe to use in a download file name. */
export function graphFileName(graphId: number, name: string | null, architecture: string): string {
  const slug = (name ?? '')
    .toLowerCase()
    .replace(/\s+/g, '-')
    .replace(/[^a-z0-9-_]+/g, '')
    .slice(0, 48) || 'graph';
  return `${graphId}_${slug}_${architecture}.json`;
}

export type ImportedNodeKind = 'ClientNode' | 'ServerNode' | 'SuperServerNode';

export interface ImportedGraph {
  nodes: Array<{ id: string; point: { x: number; y: number }; kind: ImportedNodeKind; config: Record<string, unknown> }>;
  edges: Array<{
    id: string;
    source: string;
    target: string;
    sourceHandle: string | null;
    targetHandle: string | null;
    metrics: ReturnType<typeof normalizeEdgeMetrics>;
  }>;
}

export class GraphFileError extends Error {}

const NODE_KINDS: readonly ImportedNodeKind[] = ['ClientNode', 'ServerNode', 'SuperServerNode'];

/** Upper bounds that keep a hand-edited or hostile file from freezing the editor. */
export const GRAPH_FILE_LIMITS = {
  bytes: 5 * 1024 * 1024,
  nodes: 2000,
  edges: 20000,
} as const;

/**
 * Reads a graph export (current or legacy format). Every node and edge gets a
 * fresh id, so an import can never point at entities of another graph.
 */
export function parseGraphFile(raw: unknown, createId: () => string): ImportedGraph {
  if (!isRecord(raw) || !Array.isArray(raw['nodes'])) {
    throw new GraphFileError('The file does not contain a node list.');
  }
  const rawEdges = Array.isArray(raw['edges']) ? raw['edges'] : [];
  if (raw['nodes'].length > GRAPH_FILE_LIMITS.nodes || rawEdges.length > GRAPH_FILE_LIMITS.edges) {
    throw new GraphFileError(
      `Graphs are limited to ${GRAPH_FILE_LIMITS.nodes} nodes and ${GRAPH_FILE_LIMITS.edges} edges.`,
    );
  }

  const idMap = new Map<string, string>();
  const nodes = raw['nodes'].map((entry, index): ImportedGraph['nodes'][number] => {
    const data = isRecord(entry) && isRecord(entry['data']) ? entry['data'] : {};
    const kind = data['type'];
    if (!isRecord(entry) || !NODE_KINDS.includes(kind as ImportedNodeKind)) {
      throw new GraphFileError(`Node ${index + 1} has an unknown type.`);
    }
    const id = createId();
    if (typeof entry['id'] === 'string') {
      idMap.set(entry['id'], id);
    }
    return {
      id,
      point: readPoint(entry['point']),
      kind: kind as ImportedNodeKind,
      config: readConfig(data['config']),
    };
  });

  const edges = rawEdges.map((entry, index): ImportedGraph['edges'][number] => {
    const source = isRecord(entry) ? idMap.get(String(entry['source'])) : undefined;
    const target = isRecord(entry) ? idMap.get(String(entry['target'])) : undefined;
    if (!isRecord(entry) || !source || !target) {
      throw new GraphFileError(`Edge ${index + 1} references a missing node.`);
    }
    const data = isRecord(entry['data']) ? entry['data'] : {};
    return {
      id: createId(),
      source,
      target,
      sourceHandle: typeof entry['sourceHandle'] === 'string' ? entry['sourceHandle'] : null,
      targetHandle: typeof entry['targetHandle'] === 'string' ? entry['targetHandle'] : null,
      metrics: normalizeEdgeMetrics(isRecord(data['metrics']) ? data['metrics'] : null),
    };
  });

  return { nodes, edges };
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

/** Node configs are flat settings; anything that is not a plain value is dropped. */
function readConfig(value: unknown): Record<string, string | number | boolean> {
  if (!isRecord(value)) {
    return {};
  }
  const config: Record<string, string | number | boolean> = {};
  for (const [key, entry] of Object.entries(value)) {
    const isPlain = typeof entry === 'string' || typeof entry === 'boolean'
      || (typeof entry === 'number' && Number.isFinite(entry));
    if (isPlain) {
      config[key] = entry;
    }
  }
  return config;
}

function readPoint(value: unknown): { x: number; y: number } {
  const point = isRecord(value) ? value : {};
  const coordinate = (axis: unknown) => (typeof axis === 'number' && Number.isFinite(axis) ? axis : 0);
  return { x: coordinate(point['x']), y: coordinate(point['y']) };
}
