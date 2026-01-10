from specs.client_spec import ClientSpec
from specs.server_spec import ServerSpec
import random


def estimate_training_time(
    client_spec: ClientSpec, dataset_size: int, epochs: int, model_complexity: float
):
    time_avg = (
        dataset_size * epochs * model_complexity
    ) / client_spec.performance_metrics.compute_factor
    noise = random.gauss(0, client_spec.performance_metrics.performance_stddev)

    return max(1e-6, time_avg + noise)


def estimate_aggregation_time(
    server_spec: ServerSpec, num_updates: int, model_size: int
):
    time_avg = (
        num_updates * model_size
    ) / server_spec.performance_metrics.compute_factor
    noise = random.gauss(time_avg, server_spec.performance_metrics.performance_stddev)

    return max(1e-6, time_avg + noise)
