import numpy as np
from typing import List, Dict, Any
from abc import ABC, abstractmethod

from simulation.context import get_global_context


class BaseAsyncServer(ABC):
    def __init__(self, server_id: str):
        self.server_id = server_id
        self.current_virtual_time: float = 0.0
        self.orchestrator_ref = None
        self.global_model_weights: List[np.ndarray] = []
        self._generated_events = []
        self.context = get_global_context()

    def set_orchestrator(self, orchestrator_ref):
        self.orchestrator_ref = orchestrator_ref

    def get_time(self) -> float:
        return self.current_virtual_time

    # Updated to receive direct_refs
    def handle_event(self, payload: Dict[str, Any], direct_refs: Any = None):
        event_type = payload.get("event_type")
        trigger_time = payload.get("trigger_time")
        data = payload.get("data")

        if trigger_time < self.current_virtual_time - 1e-6:
            raise ValueError(f"[Server {self.server_id}] Causality Violation!")

        self.current_virtual_time = trigger_time

        if event_type == "START_SIMULATION":
            self.start_simulation()
        elif event_type == "CLIENT_UPDATE":
            self.on_client_update(data)
        elif event_type == "SERVER_MESSAGE":
            self.on_server_message(data, direct_refs)
        else:
            print(f"[Warning] [Server {self.server_id}] Unknown event: {event_type}")

        events_to_return = self._generated_events.copy()
        self._generated_events.clear()
        return events_to_return

    def _schedule_event(
        self,
        delay: float,
        target_actor,
        event_type: str,
        data: Any = None,
        refs: Any = None,
    ):
        if self.orchestrator_ref is None:
            raise RuntimeError("Orchestrator not set!")
        trigger_time = self.current_virtual_time + delay
        payload = {"event_type": event_type, "trigger_time": trigger_time, "data": data}

        # 5-Tuple Event structure
        self._generated_events.append(
            (delay, target_actor, "handle_event", payload, refs)
        )

    def get_global_model(self) -> List[np.ndarray]:
        return self.global_model_weights

    def _get_and_clear_events(self):
        events = self._generated_events.copy()
        self._generated_events.clear()
        return events

    @abstractmethod
    def start_simulation(self):
        pass

    @abstractmethod
    def on_client_update(self, data: Any):
        pass

    @abstractmethod
    def on_server_message(self, data: Any, direct_refs: Any = None):
        pass
