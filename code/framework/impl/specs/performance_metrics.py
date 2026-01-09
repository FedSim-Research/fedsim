from dataclasses import dataclass


@dataclass
class Performance:
    compute_factor: float


performance_dict = dict[str, Performance]
