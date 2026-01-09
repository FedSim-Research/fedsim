from dataclasses import dataclass


@dataclass
class Network:
    latency_avg: int
    latency_var: int
    packet_loss_avg: int
    packet_loss_var: int


network_dict = dict[str, Network]
