/** Spyker decay and staleness modes, as the backend names them. */
export const DECAY_MODES = ['absolute', 'relative'] as const;
export type DecayMode = (typeof DECAY_MODES)[number];

export const STALENESS_MODES = ['reciprocal', 'none', 'delta', 'relative'] as const;
export type StalenessMode = (typeof STALENESS_MODES)[number];
