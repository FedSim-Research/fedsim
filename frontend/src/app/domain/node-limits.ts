import { Architecture, NodeKind } from './topology';

/** How many nodes of a kind a graph may hold; kinds without an entry are unlimited. */
const NODE_LIMITS: Record<Architecture, Partial<Record<NodeKind, number>>> = {
  hierfl: { SuperServerNode: 1 },
  spyker: { SuperServerNode: 0 },
};

const LIMIT_MESSAGES: Record<Architecture, Partial<Record<NodeKind, string>>> = {
  hierfl: { SuperServerNode: 'Only one Super Server can exist in a hierarchical graph.' },
  spyker: { SuperServerNode: 'No super server is allowed to exist in the Spyker Environment' },
};

/** Returns why `added` cannot join a graph that already holds `existing`, or null if it can. */
export function nodeLimitViolation(
  architecture: Architecture,
  existing: readonly NodeKind[],
  added: readonly NodeKind[],
): string | null {
  for (const [kind, limit] of Object.entries(NODE_LIMITS[architecture]) as [NodeKind, number][]) {
    const adding = added.filter((entry) => entry === kind).length;
    if (adding > 0 && existing.filter((entry) => entry === kind).length + adding > limit) {
      return LIMIT_MESSAGES[architecture][kind] ?? `Too many ${kind} nodes.`;
    }
  }
  return null;
}
