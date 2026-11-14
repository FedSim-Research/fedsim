from dataclasses import dataclass


@dataclass
class Network:
    latency_avg: float  # in ms
    latency_stddev: float  # in ms
    packet_loss_avg: float  # from 0 to 1
    packet_loss_stddev: float  # from 0 to 1
