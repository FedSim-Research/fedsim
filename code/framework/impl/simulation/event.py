from dataclasses import dataclass
from typing import Any


@dataclass
class Event:
    trigger_time: int
    callback: function
    payload: Any
