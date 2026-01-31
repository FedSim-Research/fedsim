import heapq
import ray
from typing import List
from simulation.event import Event


@ray.remote
class SimulationOrchestrator:
    def __init__(self):
        self._event_heap: List[Event] = []
        self.global_virtual_time: float = 0.0
        self._sequence_counter: int = 0

    def add_event(self, delay: float, actor_ref, method_name: str, payload):
        self._check_precons_add_event(delay, actor_ref, method_name)

        self._add_event_internal(delay, actor_ref, method_name, payload)

    def step(self):
        if not self._event_heap:
            return None

        event = heapq.heappop(self._event_heap)
        self.global_virtual_time = max(self.global_virtual_time, event.trigger_time)
        actor_ref, method_name, payload = event.callback
        print(
            "[Orchestrator] Executing event:",
            payload["event_type"],
            "at time",
            self.global_virtual_time,
            "for",
            actor_ref,
        )
        return getattr(actor_ref, method_name).remote(payload)

    def run_until(self, target_time: float):
        self._check_precons_run_until(target_time)

        while self._event_heap:
            next_event = self._event_heap[0]
            if next_event.trigger_time > target_time:
                self.global_virtual_time = target_time
                break

            # Execute the event
            future_result = self.step()

            # --- DEBUGGING: WAIT FOR RESULT ---
            # If the actor crashed, this line will raise the Exception here and now.
            # Comment this out later for maximum performance.
            if future_result is not None:
                new_events_data = ray.get(future_result)

                # 3. Process new events (if any returned)
                if new_events_data:
                    for delay, target, method, payload in new_events_data:
                        # Reuse the logic of add_event locally
                        self._add_event_internal(delay, target, method, payload)
            # ----------------------------------

    def _add_event_internal(self, delay, actor_ref, method_name, payload):
        """Helper to add event without being an Actor method"""
        trigger_time = self.global_virtual_time + delay
        self._sequence_counter += 1
        event = Event(
            trigger_time=trigger_time,
            sequence_id=self._sequence_counter,
            callback=(actor_ref, method_name, payload),
        )
        heapq.heappush(self._event_heap, event)

    def _check_precons_add_event(self, delay, actor_ref, method_name):
        if delay < 0:
            raise ValueError("Delay cannot be negative.")
        if actor_ref is None:
            raise TypeError("Actor reference cannot be None.")

        # Basic validation. Note: Ray actors are dynamic, so strict
        # method checking is hard without reflection, but we can try basic access.
        try:
            getattr(actor_ref, method_name)
        except AttributeError:
            raise ValueError(f"Method '{method_name}' not found on actor.")

    def _check_precons_run_until(self, target_time):
        if target_time < self.global_virtual_time:
            raise ValueError(
                f"Target time ({target_time}) is in the past "
                f"(Current: {self.global_virtual_time})"
            )
