"""Translate editor performance settings into the shared runtime model."""

import math
from typing import Any

from fedsim.specs.performance_metrics import Performance


def parse_node_performance(node_type: str, config: dict[str, Any], *, prefix: str) -> Performance:
    if config.get("computeFactor") is None:
        raise ValueError(f"{prefix}_missing_{node_type}_computeFactor")
    try:
        compute_factor = float(config["computeFactor"])
    except (TypeError, ValueError):
        raise ValueError(f"{prefix}_invalid_{node_type}_computeFactor") from None
    if not math.isfinite(compute_factor) or compute_factor <= 0:
        raise ValueError(f"{prefix}_invalid_{node_type}_computeFactor")

    raw_sigma = config.get("performanceSigma")
    try:
        sigma_seconds = 0.0 if raw_sigma is None else float(raw_sigma)
    except (TypeError, ValueError):
        raise ValueError(f"{prefix}_invalid_{node_type}_performanceSigma") from None
    if not math.isfinite(sigma_seconds) or sigma_seconds < 0:
        raise ValueError(f"{prefix}_invalid_{node_type}_performanceSigma")
    return Performance(compute_factor=compute_factor, performance_stddev=sigma_seconds)
