from specs.client_spec import ClientSpec
from specs.server_spec import ServerSpec
from specs.network_metrics import Network
import random


def estimate_transmission_time(
    sender_spec: ClientSpec | ServerSpec,
    receiver_spec: ClientSpec | ServerSpec,
    network_metrics: dict[str, Network],
    metrics_id: str,
    payload_size_mb: float,
) -> float:
    # We treat packet loss as a reduction in effective throughput (TCP throughput model approximation)
    # Assuming packet_loss_avg is a percentage (0.0 to 1.0).
    packet_loss = random.gauss(
        network_metrics[metrics_id].packet_loss_avg,
        network_metrics[metrics_id].packet_loss_stddev,
    )

    throughput_factor = max(0.001, 1.0 - packet_loss)

    bottleneck_mbps = (
        min(
            sender_spec.upload_speed,
            receiver_spec.download_speed,
        )
        * throughput_factor
    )

    payload_size_mbits = 8 * payload_size_mb
    transmission_delay_sec = payload_size_mbits / bottleneck_mbps

    latency_ms = random.gauss(
        network_metrics[metrics_id].latency_avg,
        network_metrics[metrics_id].latency_stddev,
    )

    latency_sec = (latency_ms) / 1000.0
    latency_sec = max(0.0, latency_sec)

    return transmission_delay_sec + latency_sec
