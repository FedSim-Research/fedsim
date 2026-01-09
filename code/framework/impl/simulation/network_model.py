from specs.client_spec import ClientSpec
from specs.server_spec import ServerSpec
import random


def estimate_transmission_time(
    sender_spec: ClientSpec | ServerSpec,
    receiver_spec: ClientSpec | ServerSpec,
    payload_size_mb: float,
) -> float:
    # We treat packet loss as a reduction in effective throughput (TCP throughput model approximation)
    # Assuming packet_loss_avg is a percentage (0.0 to 1.0).
    sender_loss = sender_spec.network_metrics.packet_loss_avg
    receiver_loss = receiver_spec.network_metrics.packet_loss_avg

    # Conservative estimate: max loss determines flow stability
    worst_loss = max(sender_loss, receiver_loss)

    throughput_factor = max(0.1, 1.0 - worst_loss)

    bottleneck_mbps = (
        min(
            sender_spec.network_metrics.upload_speed,
            receiver_spec.network_metrics.download_speed,
        )
        * throughput_factor
    )

    payload_size_mbits = 8 * payload_size_mb
    transmission_delay_sec = payload_size_mbits / bottleneck_mbps

    sender_latency_ms = random.gauss(
        sender_spec.network_metrics.latency_avg,
        sender_spec.network_metrics.latency_stddev,
    )

    receiver_latency_ms = random.gauss(
        receiver_spec.network_metrics.latency_avg,
        receiver_spec.network_metrics.latency_stddev,
    )

    total_latency_sec = (sender_latency_ms + receiver_latency_ms) / 1000.0
    total_latency_sec = max(0.0, total_latency_sec)

    return transmission_delay_sec + total_latency_sec
