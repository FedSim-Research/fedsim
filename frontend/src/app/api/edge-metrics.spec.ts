import { EDGE_METRIC_DEFAULTS, normalizeEdgeMetrics } from './edge-metrics';

describe('normalizeEdgeMetrics', () => {
  it('falls back to defaults for missing or non-numeric values', () => {
    expect(normalizeEdgeMetrics(null)).toEqual(EDGE_METRIC_DEFAULTS);
    expect(normalizeEdgeMetrics({ pingMs: 'abc', jitterMs: undefined })).toEqual(EDGE_METRIC_DEFAULTS);
  });

  it('rounds latency values and clamps probabilities', () => {
    expect(normalizeEdgeMetrics({ pingMs: 12.6, jitterMs: -3, packetloss: 1.5, packetlossStddev: -0.1 })).toEqual({
      pingMs: 13,
      jitterMs: 0,
      packetloss: 1,
      packetlossStddev: 0,
    });
  });
});
