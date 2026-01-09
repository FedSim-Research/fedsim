import heapq
from typing import List
from simulation.event import Event


class SimulationOrchestrator:
    def __init__(self):
        self._event_heap: List[Event] = []
        self.global_virtual_time: float = 0.0
        self._sequence_counter: int = 0

    def add_event(self, delay: float, actor_ref, method_name: str, payload):
        self._check_precons_add_event(delay, actor_ref, method_name)

        trigger_time = self.global_virtual_time + delay
        self._sequence_counter += 1

        event = Event(
            trigger_time=trigger_time,
            sequence_id=self._sequence_counter,
            callback=(actor_ref, method_name, payload),
        )

        heapq.heappush(self._event_heap, event)

    def step(self):
        if not self._event_heap:
            return None

        event = heapq.heappop(self._event_heap)
        self.global_virtual_time = max(self.global_virtual_time, event.trigger_time)
        actor_ref, method_name, payload = event.callback

        return getattr(actor_ref, method_name).remote(payload)

    def run_until(self, target_time: float):
        self._check_precons_run_until(target_time)

        while self._event_heap:
            next_event = self._event_heap[0]
            if next_event.trigger_time > target_time:
                self.global_virtual_time = target_time
                break

            self.step()

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
