import { Connection, StaticEdge as Edge, StaticNode as Node } from 'ngx-vflow';
import { canLink } from '../domain/link-rules';
import { Architecture, NodeKind } from '../domain/topology';

/** Position in the hierarchy; links always run from the upper to the lower node. */
const RANK: Record<NodeKind, number> = { SuperServerNode: 0, ServerNode: 1, ClientNode: 2 };

/** Handles used for a link, keyed by `${upperKind}>${lowerKind}`. */
const LINK_HANDLES: Record<string, { sourceHandle: string; targetHandle: string }> = {
  'SuperServerNode>ServerNode': { sourceHandle: 'superserver-out', targetHandle: 'server-in-top' },
  'ServerNode>ClientNode': { sourceHandle: 'server-out-bottom', targetHandle: 'client-in' },
  'ServerNode>ServerNode': { sourceHandle: 'server-out', targetHandle: 'server-in' },
};

/** Handle reserved for clients; peer servers must not use it. */
const CLIENT_HANDLE = 'server-out-bottom';

/** Decides whether the user may draw `connection` in the current graph. */
export function canConnect(
  architecture: Architecture,
  nodes: Node[],
  edges: Edge[],
  connection: Connection,
): boolean {
  const source = findNode(nodes, connection.source);
  const target = findNode(nodes, connection.target);
  if (!source || !target || !canLink(architecture, kindOf(source), kindOf(target))) {
    return false;
  }
  if (edges.some((edge) => links(edge, source.id, target.id))) {
    return false;
  }
  const kinds = [kindOf(source), kindOf(target)];
  if (kinds[0] === 'ServerNode' && kinds[1] === 'ServerNode') {
    return connection.sourceHandle !== CLIENT_HANDLE && connection.targetHandle !== CLIENT_HANDLE;
  }
  // A client belongs to exactly one server.
  const client = kinds[0] === 'ClientNode' ? source : kinds[1] === 'ClientNode' ? target : null;
  return !client || !edges.some((edge) => edge.source === client.id || edge.target === client.id);
}

/** Orients a connection from the upper to the lower node and picks the matching handles. */
export function normalizeConnection(nodes: Node[], connection: Connection): Connection {
  const first = findNode(nodes, connection.source);
  const second = findNode(nodes, connection.target);
  if (!first || !second) {
    return connection;
  }
  const [upper, lower] = isAbove(first, second) ? [first, second] : [second, first];
  const handles = LINK_HANDLES[`${kindOf(upper)}>${kindOf(lower)}`];
  if (!handles) {
    return connection;
  }
  return { source: upper.id, target: lower.id, ...handles };
}

/**
 * Re-orients server-to-server links so they run left to right after nodes moved.
 * Returns the same array when nothing changed.
 */
export function orientServerLinks(nodes: Node[], edges: Edge[]): Edge[] {
  let changed = false;
  const oriented = edges.map((edge) => {
    const source = findNode(nodes, edge.source);
    const target = findNode(nodes, edge.target);
    if (!source || !target || kindOf(source) !== 'ServerNode' || kindOf(target) !== 'ServerNode') {
      return edge;
    }
    const next = normalizeConnection(nodes, edge);
    const same = next.source === edge.source && next.target === edge.target
      && next.sourceHandle === edge.sourceHandle && next.targetHandle === edge.targetHandle;
    if (same) {
      return edge;
    }
    changed = true;
    return { ...edge, ...next };
  });
  return changed ? oriented : edges;
}

function isAbove(first: Node, second: Node): boolean {
  const rankDifference = RANK[kindOf(first)] - RANK[kindOf(second)];
  if (rankDifference !== 0) {
    return rankDifference < 0;
  }
  // Peers are ordered left to right.
  return (first.point?.x ?? 0) <= (second.point?.x ?? 0);
}

function links(edge: Edge, first: string, second: string): boolean {
  return (edge.source === first && edge.target === second) || (edge.source === second && edge.target === first);
}

function findNode(nodes: Node[], id: string): Node | undefined {
  return nodes.find((node) => node.id === id);
}

function kindOf(node: Node): NodeKind {
  return (node as { data?: { type?: NodeKind } }).data?.type as NodeKind;
}
