"""Serializable logical client addresses; they do not allocate Ray processes."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClientHandle:
    execution_id: str
    client_id: str
    client_config: dict[str, Any]
    context_ref: Any

    def handle_event(self, *args, **kwargs):
        raise RuntimeError("Logical clients must be dispatched through the CPU execution pool")
