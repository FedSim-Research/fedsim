"""Translate editor performance settings into the shared runtime model."""

from typing import Any

from fedsim.services.input_values import parse_nonnegative_float, parse_positive_float
from fedsim.specs.performance_metrics import Performance


def parse_node_performance(node_type: str, config: dict[str, Any], *, prefix: str) -> Performance:
    if config.get("computeFactor") is None:
        raise ValueError(f"{prefix}_missing_{node_type}_computeFactor")
    compute_factor = parse_positive_float(
        config["computeFactor"], f"{prefix}_invalid_{node_type}_computeFactor"
    )
    raw_sigma = config.get("performanceSigma")
    sigma_seconds = (
        0.0
        if raw_sigma is None
        else parse_nonnegative_float(raw_sigma, f"{prefix}_invalid_{node_type}_performanceSigma")
    )
    return Performance(compute_factor=compute_factor, performance_stddev=sigma_seconds)
