from dataclasses import dataclass, field
from typing import Any, Tuple


@dataclass(order=True)
class Event:
    trigger_time: float
    sequence_id: int
    callback: Tuple[Any, str, Any] = field(compare=False)
    """callback = (actor_ref, method_name, payload)"""

    def __post_init__(self):
        if self.trigger_time < 0:
            raise ValueError("trigger_time cannot be negative.")
        if self.callback[0] is None:
            raise TypeError("actor_ref in callback cannot be None.")
