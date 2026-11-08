from dataclasses import dataclass


@dataclass
class Performance:
    """Work-rate factor and additive runtime standard deviation in seconds."""

    compute_factor: float
    performance_stddev: float
