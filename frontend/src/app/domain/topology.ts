/** Federated-learning architectures the simulator supports. */
export type Architecture = 'spyker' | 'hierfl';

/** What a run reports: one architecture or a paired run of both. */
export type RunArchitecture = Architecture | 'both';

/** Resolves a backend architecture name; the backend says `hierarchical` or `hierfl` for the same thing. */
export function parseRunArchitecture(value: unknown): RunArchitecture | null {
  if (value === 'hierfl' || value === 'hierarchical') {
    return 'hierfl';
  }
  return value === 'spyker' || value === 'both' ? value : null;
}

/** Node kinds as the backend names them. */
export type NodeKind = 'ClientNode' | 'ServerNode' | 'SuperServerNode';

export const NODE_KINDS: readonly NodeKind[] = ['ClientNode', 'ServerNode', 'SuperServerNode'];

export function isNodeKind(value: unknown): value is NodeKind {
  return NODE_KINDS.includes(value as NodeKind);
}
