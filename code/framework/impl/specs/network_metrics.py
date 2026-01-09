from dataclasses import dataclass


@dataclass
class Network:
    latency_avg: int  # in ms
    latency_stddev: int  # in ms
    packet_loss_avg: int  # from 0 to 1
    packet_loss_stddev: int  # from 0 to 1
    upload_speed: float  # in Mbps
    download_speed: float  # in Mbps
    memory_limit: float  # in MB


network_dict = dict[str, Network]
