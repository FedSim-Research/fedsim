import { StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { normalizeEdgeMetrics } from '../api/edge-metrics';
import { VflowGraph } from '../api/graph-api.service';
import { Architecture } from '../domain/topology';

interface NodePayloadData {
  type?: VflowGraph['nodes'][number]['data']['type'];
  config?: Record<string, unknown>;
}

/** Builds the payload for `PUT /graphs/{id}/state` from editor state. */
export function toVflowGraph(architecture: Architecture, nodes: Node[], edges: Edge[]): VflowGraph {
  const typedNodes = nodes.filter((node) => nodeData(node).type !== undefined);
  const nodeIds = new Set(typedNodes.map((node) => node.id));
  return {
    nodes: typedNodes.map((node) => {
      const data = nodeData(node);
      const type = data.type!;
      return {
        id: node.id,
        point: { x: finiteOr(node.point?.x, 0), y: finiteOr(node.point?.y, 0) },
        type,
        data: { type, config: data.config ?? {}, environment: architecture, fromJson: true, selected: false },
      };
    }),
    edges: edges.filter((edge) => nodeIds.has(edge.source) && nodeIds.has(edge.target)).map((edge) => ({
      id: edge.id,
      source: edge.source,
      target: edge.target,
      config: normalizeEdgeMetrics((edge as { data?: { metrics?: Record<string, unknown> } }).data?.metrics),
      sourceHandle: edge.sourceHandle ?? null,
      targetHandle: edge.targetHandle ?? null,
      reconnectable: edge.reconnectable !== false,
      floating: edge.floating ?? false,
    })),
  };
}

function nodeData(node: Node): NodePayloadData {
  return (node as { data?: NodePayloadData }).data ?? {};
}

function finiteOr(value: unknown, fallback: number): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : fallback;
}
