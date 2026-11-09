import random

from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.network_metrics import Network
from fedsim.specs.server_spec import ServerSpec


def estimate_transmission_time(
    sender_spec: ClientSpec | ServerSpec,
    receiver_spec: ClientSpec | ServerSpec,
    network_metrics: dict[str, Network],
    metrics_id: str,
    payload_size_bytes: int,
    *,
    rng: random.Random | None = None,
) -> float:
    """Estimate virtual transfer seconds from payload bytes and decimal Mbps."""
    rng = random if rng is None else rng
    # We treat packet loss as a reduction in effective throughput (TCP throughput model approximation)
    # Assuming packet_loss_avg is a percentage (0.0 to 1.0).
    packet_loss = rng.gauss(
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

    payload_size_bits = 8 * payload_size_bytes
    transmission_delay_sec = payload_size_bits / (bottleneck_mbps * 1_000_000)

    latency_ms = rng.gauss(
        network_metrics[metrics_id].latency_avg,
        network_metrics[metrics_id].latency_stddev,
    )

    latency_sec = (latency_ms) / 1000.0
    latency_sec = max(0.0, latency_sec)

    return transmission_delay_sec + latency_sec
