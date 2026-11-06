from dataclasses import dataclass


@dataclass
class Network:
    latency_avg: int  # in ms
    latency_stddev: int  # in ms
    packet_loss_avg: float  # from 0 to 1
    packet_loss_stddev: float  # from 0 to 1
