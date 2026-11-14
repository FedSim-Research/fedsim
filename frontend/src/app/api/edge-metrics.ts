export interface EdgeMetrics {
  pingMs: number;
  jitterMs: number;
  packetloss: number;
  packetlossStddev: number;
}

export const EDGE_METRIC_DEFAULTS: EdgeMetrics = {
  pingMs: 20,
  jitterMs: 2,
  packetloss: 0.001,
  packetlossStddev: 0.0001,
};

interface MetricBounds {
  min: number;
  max?: number;
  /** The backend stores ping and jitter as integers. */
  integer?: boolean;
}

export const EDGE_METRIC_BOUNDS: Record<keyof EdgeMetrics, MetricBounds> = {
  pingMs: { min: 0, integer: true },
  jitterMs: { min: 0, integer: true },
  packetloss: { min: 0, max: 1 },
  packetlossStddev: { min: 0, max: 1 },
};

/** Clamps a single metric into its valid range, falling back to the default when not numeric. */
export function normalizeEdgeMetric(field: keyof EdgeMetrics, value: unknown): number {
  const numeric = Number(value);
  if (value === null || value === undefined || value === '' || !Number.isFinite(numeric)) {
    return EDGE_METRIC_DEFAULTS[field];
  }
  const { min, max, integer } = EDGE_METRIC_BOUNDS[field];
  const rounded = integer ? Math.round(numeric) : numeric;
  const bounded = Math.max(min, rounded);
  return max === undefined ? bounded : Math.min(max, bounded);
}

export function normalizeEdgeMetrics(metrics?: Partial<Record<keyof EdgeMetrics, unknown>> | null): EdgeMetrics {
  const source = metrics ?? {};
  return {
    pingMs: normalizeEdgeMetric('pingMs', source.pingMs),
    jitterMs: normalizeEdgeMetric('jitterMs', source.jitterMs),
    packetloss: normalizeEdgeMetric('packetloss', source.packetloss),
    packetlossStddev: normalizeEdgeMetric('packetlossStddev', source.packetlossStddev),
  };
}
