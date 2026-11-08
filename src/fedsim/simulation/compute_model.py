import random

from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.server_spec import ServerSpec


def _with_runtime_noise(time_avg: float, sigma_seconds: float) -> float:
    noise = 0.0 if sigma_seconds == 0 else random.gauss(0, sigma_seconds)
    return max(1e-6, time_avg + noise)


def estimate_training_time(
    client_spec: ClientSpec, dataset_size: int, epochs: int, model_complexity: float
):
    time_avg = (
        dataset_size * epochs * model_complexity
    ) / client_spec.performance_metrics.compute_factor
    return _with_runtime_noise(time_avg, client_spec.performance_metrics.performance_stddev)


def estimate_aggregation_time(server_spec: ServerSpec, num_updates: int, model_size: int):
    time_avg = (num_updates * model_size) / server_spec.performance_metrics.compute_factor
    return _with_runtime_noise(time_avg, server_spec.performance_metrics.performance_stddev)
