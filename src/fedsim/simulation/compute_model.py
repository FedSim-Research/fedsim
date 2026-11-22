import math
import random

from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.server_spec import ServerSpec


def _with_runtime_noise(
    time_avg: float, sigma_seconds: float, rng: random.Random | None = None
) -> float:
    rng = random if rng is None else rng
    noise = 0.0 if sigma_seconds == 0 else rng.gauss(0, sigma_seconds)
    return max(1e-6, time_avg + noise)


def estimate_training_time(
    client_spec: ClientSpec,
    dataset_size: int,
    epochs: int,
    model_complexity: float,
    *,
    rng: random.Random | None = None,
):
    time_avg = (
        dataset_size * epochs * model_complexity
    ) / client_spec.performance_metrics.compute_factor
    return _with_runtime_noise(time_avg, client_spec.performance_metrics.performance_stddev, rng)


def require_aggregation_throughput(value):
    if value is None:
        raise ValueError("aggregation_throughput_required")
    try:
        valid = not isinstance(value, bool) and math.isfinite(value) and value > 0
    except (TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("invalid_aggregation_throughput")
    return float(value)


def estimate_aggregation_time(
    server_spec: ServerSpec,
    num_updates: int,
    model_size: int,
    *,
    rng: random.Random | None = None,
    throughput_bytes_per_second: float | None = None,
):
    """Response delay from explicit input bytes/second, independent of training.

    The supplied throughput requires workload calibration. This approximation
    does not model a server queue or delayed state visibility.
    """
    throughput = require_aggregation_throughput(throughput_bytes_per_second)
    time_avg = (num_updates * model_size) / throughput
    return _with_runtime_noise(time_avg, server_spec.performance_metrics.performance_stddev, rng)
