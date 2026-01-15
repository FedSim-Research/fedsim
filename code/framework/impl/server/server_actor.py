import numpy as np
from typing import List, Dict, Any
from abc import ABC, abstractmethod

from simulation.context import get_global_context


class BaseAsyncServer(ABC):
    """
    Abstract Base Class for Ray Actor Servers.
    """

    def __init__(self, server_id: str):
        self.server_id = server_id

        # Simulation Physics State
        self.current_virtual_time: float = 0.0
        self.orchestrator_ref = None  # Must be set after creation

        # Machine Learning State
        # We store parameters as a list of numpy arrays (standard Flower format)
        self.global_model_weights: List[np.ndarray] = []

        self._generated_events = []

        # Context Access
        self.context = get_global_context()

    def set_orchestrator(self, orchestrator_ref):
        """Link this server to the Simulation Orchestrator."""
        self.orchestrator_ref = orchestrator_ref

    def get_time(self) -> float:
        return self.current_virtual_time

    # =========================================================
    # THE MAIN EVENT ENTRY POINT
    # =========================================================
    def handle_event(self, payload: Dict[str, Any]):
        """
        Payload Structure:
        {
            "event_type": str,       # REQUIRED: "CLIENT_UPDATE", "START_SIMULATION", "SERVER_MESSAGE", etc.
            "trigger_time": float,   # REQUIRED: The time this event was scheduled to happen
            "data": Any              # Optional: The actual content (weights, tokens, etc.)
        }
        """
        event_type = payload.get("event_type")
        trigger_time = payload.get("trigger_time")
        data = payload.get("data")

        if trigger_time < self.current_virtual_time - 1e-6:
            raise ValueError(
                f"[Server {self.server_id}] Causality Violation! "
                f"Event {event_type} triggered at {trigger_time} "
                f"but local time is already {self.current_virtual_time}"
            )

        self.current_virtual_time = trigger_time

        if event_type == "START_SIMULATION":
            self.start_simulation()
        elif event_type == "CLIENT_UPDATE":
            self.on_client_update(data)
        elif event_type == "SERVER_MESSAGE":
            self.on_server_message(data)
        else:
            print(
                f"[Warning] [Server {self.server_id}] Unknown event type: {event_type}"
            )

        events_to_return = self._generated_events.copy()
        self._generated_events.clear()
        return events_to_return

    def _schedule_event(
        self, delay: float, target_actor, event_type: str, data: Any = None
    ):
        """
        Helper to make scheduling cleaner in subclasses.
        """
        if self.orchestrator_ref is None:
            raise RuntimeError("Orchestrator not set! Call set_orchestrator() first.")

        trigger_time = self.current_virtual_time + delay

        payload = {"event_type": event_type, "trigger_time": trigger_time, "data": data}

        self._generated_events.append((delay, target_actor, "handle_event", payload))

    def get_global_model(self) -> List[np.ndarray]:
        """Return the current global model weights."""
        return self.global_model_weights

    def _get_and_clear_events(self):
        """Helper to flush the event buffer."""
        events = self._generated_events.copy()
        self._generated_events.clear()
        return events

    # =========================================================
    # ABSTRACT METHODS ("Hooks" for Hierarchical and Spyker)
    # =========================================================
    @abstractmethod
    def start_simulation(self):
        """
        Called once at the beginning (t=0).
        - Hierarchical Super: Sends initial model to Edges.
        - Hierarchical Edge: Do nothing (wait for Super).
        - Spyker: Send initial model to Clients.
        """
        pass

    @abstractmethod
    def on_client_update(self, data: Any):
        """
        Handle a result from a Client.
        data = FitRes metrics, weights, etc.
        """
        pass

    @abstractmethod
    def on_server_message(self, data: Any):
        """
        Handle a message from another Server (Edge<->Super or Peer->Peer).
        """
        pass
