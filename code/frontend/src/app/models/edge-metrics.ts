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
