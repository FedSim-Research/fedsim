import hashlib
import heapq
import json
import os
import queue
import threading
from typing import Dict, List

import ray

from fedsim.simulation.event import Event


def _event_log_enabled() -> bool:
    return os.environ.get("FEDSIM_EVENT_LOG", "on").strip().lower() != "off"


@ray.remote(num_cpus=0, num_gpus=0)
class SimulationOrchestrator:
    def __init__(self, cpu_pool=None, event_order: str = "completion"):
        if event_order not in {"completion", "parent"}:
            raise ValueError("event_order must be completion or parent")
        self.event_order = event_order
        self._cpu_pool = cpu_pool
        self._event_heap: List[Event] = []
        self.global_virtual_time: float = 0.0
        self._sequence_counter: int = 0
        self._order_digest = hashlib.sha256()
        self._dispatch_counts = {}
        self._client_update_counts = {}

        self._event_log_on = _event_log_enabled()
        self._log_queue = None
        if self._event_log_on:
            self._log_queue = queue.Queue()
            self._log_thread = threading.Thread(
                target=self._log_worker, daemon=True, name="AsyncLogger"
            )
            self._log_thread.start()

    def add_event(self, delay: float, actor_ref, method_name: str, payload, refs=None):
        """Used externally to seed the initial simulation events."""
        self._check_precons_add_event(delay, actor_ref, method_name)
        trigger_time = self.global_virtual_time + delay
        self._add_event_internal(trigger_time, actor_ref, method_name, payload, refs)

    def run_until(self, target_time: float):
        self._check_precons_run_until(target_time)

        # Track running futures to execute concurrent events without ray.get() blocking
        in_flight: Dict[ray.ObjectRef, Event] = {}
        completed_batch = []

        while True:
            # 1. Advance Time Safely
            # We only advance global_virtual_time if no tasks are executing.
            # This ensures we don't jump ahead while a running actor might still generate an event in the past.
            if not in_flight:
                if not self._event_heap or self._event_heap[0].trigger_time > target_time:
                    break  # Simulation target reached

                self.global_virtual_time = self._event_heap[0].trigger_time

            # 2. Dispatch events eligible at the current virtual time.
            # Callbacks can share actor state; actor serialization and CPU admission
            # constrain concurrency. Completion order affects child-event insertion.
            while self._event_heap:
                next_event = self._event_heap[0]

                # Allow a small timestamp tolerance for floating-point rounding.
                if next_event.trigger_time <= self.global_virtual_time + 1e-6:
                    if next_event.trigger_time > target_time:
                        break

                    event = heapq.heappop(self._event_heap)
                    actor_ref, method_name, payload, refs = event.callback
                    event_type = payload.get("event_type", "UNKNOWN")
                    raw_data = payload.get("data")
                    data = raw_data if isinstance(raw_data, dict) else {}
                    self._dispatch_counts[event_type] = self._dispatch_counts.get(event_type, 0) + 1
                    if event_type == "CLIENT_UPDATE":
                        client_id = data.get("client_id")
                        self._client_update_counts[client_id] = (
                            self._client_update_counts.get(client_id, 0) + 1
                        )
                    self._order_digest.update(
                        json.dumps(
                            [
                                event.trigger_time,
                                event_type,
                                *[
                                    data.get(key)
                                    for key in (
                                        "client_id",
                                        "server_id",
                                        "type",
                                        "sender_id",
                                        "bid",
                                    )
                                ],
                            ],
                            separators=(",", ":"),
                        ).encode()
                        + b"\n"
                    )

                    if self._event_log_on:
                        self._log_queue.put((self.global_virtual_time, payload))

                    # Dispatch to the Ray cluster asynchronously
                    kwargs = {} if refs is None else {"direct_refs": refs}
                    if payload.get("event_type") in {"START_FIT", "EVALUATE"}:
                        if self._cpu_pool is None:
                            raise RuntimeError("CPU execution pool required for compute events")
                        future = self._cpu_pool.call.remote(
                            actor_ref, method_name, (payload,), kwargs
                        )
                    else:
                        future = getattr(actor_ref, method_name).remote(payload, **kwargs)

                    in_flight[future] = event

                else:
                    # The next event is strictly in the future. We must wait for current batch to finish.
                    break

            # 3. Asynchronous Resolution
            if in_flight:
                # Wait for AT LEAST ONE future to finish so we can parse its generated events
                done_refs, _ = ray.wait(list(in_flight.keys()), num_returns=1)

                for done_ref in done_refs:
                    # Pop the finished event's tracking context
                    completed_event = in_flight.pop(done_ref)

                    try:
                        new_events_data = ray.get(done_ref)
                        if self.event_order == "parent":
                            # Finish this dispatch frontier before exposing its
                            # children. Sorting only the currently-ready futures
                            # would still depend on physical completion timing.
                            completed_batch.append((completed_event, new_events_data))
                            continue
                        self._add_generated_events(completed_event, new_events_data)

                    except Exception as e:
                        print(f"Simulation Actor Crashed processing event {completed_event}: {e}")
                        raise e

                if self.event_order == "parent" and not in_flight:
                    for parent, children in sorted(
                        completed_batch, key=lambda entry: entry[0].sequence_id
                    ):
                        self._add_generated_events(parent, children)
                    completed_batch.clear()

        # Ensure timer aligns with target limit
        self.global_virtual_time = max(self.global_virtual_time, target_time)

    def _add_generated_events(self, parent, children):
        for child in children or ():
            if len(child) not in (4, 5):
                raise ValueError(f"Unexpected event tuple length: {len(child)}")
            delay, target, method, payload, *refs = child
            if delay < 0:
                raise ValueError(f"Negative delay {delay} generated by event.")
            # Child times are relative to their own parent, never wall time.
            self._add_event_internal(
                parent.trigger_time + delay, target, method, payload, refs[0] if refs else None
            )

    def get_execution_summary(self):
        return {
            "event_order": self.event_order,
            "virtual_time": self.global_virtual_time,
            "dispatch_counts": dict(self._dispatch_counts),
            "client_update_counts": dict(self._client_update_counts),
            "order_sha256": self._order_digest.hexdigest(),
            "digest_scope": "Ordered virtual time, event type, client/server IDs, message type/sender/broadcast ID; excludes model payloads and physical execution.",
        }

    def _add_event_internal(
        self, trigger_time: float, actor_ref, method_name: str, payload, refs=None
    ):
        """Helper to add event utilizing absolute timestamps."""
        self._sequence_counter += 1
        event = Event(
            trigger_time=trigger_time,
            sequence_id=self._sequence_counter,
            callback=(actor_ref, method_name, payload, refs),
        )
        heapq.heappush(self._event_heap, event)

    def _check_precons_add_event(self, delay, actor_ref, method_name):
        if delay < 0:
            raise ValueError("Delay cannot be negative.")
        if actor_ref is None:
            raise TypeError("Actor reference cannot be None.")
        try:
            getattr(actor_ref, method_name)
        except AttributeError:
            raise ValueError(f"Method '{method_name}' not found on actor.")

    def _check_precons_run_until(self, target_time):
        if target_time < self.global_virtual_time:
            raise ValueError(
                f"Target time ({target_time}) is in the past (Current: {self.global_virtual_time})"
            )

    def _log_worker(self):
        """Background thread that formats and prints logs in batches to avoid I/O blocking."""
        while True:
            try:
                # Block until at least one log is available
                v_time, payload = self._log_queue.get(timeout=1.0)
            except queue.Empty:
                continue

            batch = [(v_time, payload)]

            # Rapidly drain the queue to form a batch
            while not self._log_queue.empty():
                try:
                    batch.append(self._log_queue.get_nowait())
                except queue.Empty:
                    break

            logs_to_print = []
            current_thread = threading.current_thread().name

            # Format the entire batch
            for vt, pld in batch:
                event_type = pld.get("event_type", "UNKNOWN")
                log_message = f"[Orchestrator] t={vt:09.3f} | {event_type}"

                if event_type == "SERVER_MESSAGE":
                    data = pld.get("data", {})
                    sub_type = data.get("type", "RAW")
                    sender = data.get("sender_id") or data.get("edge_server_id") or "?"

                    log_message += f" ({sub_type})".ljust(20) + f" from {sender}"

                    if sub_type == "TOKEN":
                        ages = data.get("server_ages", {})
                        age_str = ", ".join(
                            [f"{k.replace('server_', '')}:{v}" for k, v in ages.items()]
                        )
                        log_message += f" [Knowledge: {age_str}]"

                    elif sub_type == "MODEL_BROADCAST":
                        age = data.get("age", -1)
                        bid = data.get("bid", "N/A")
                        log_message += f" [Age: {age} | BID: {bid}]"

                    elif sub_type == "AGGREGATION_SYNC":
                        samples = data.get("num_samples", 0)
                        log_message += f" [Samples: {samples}]"

                elif event_type == "CLIENT_UPDATE":
                    data = pld.get("data", {})
                    cid = data.get("client_id", "unknown")
                    sid = data.get("server_id", "?")
                    log_message += f" from {cid} (on {sid})"

                elif event_type == "START_FIT":
                    data = pld.get("data", {})
                    sid = data.get("server_id", "?")
                    log_message += f" initiated by {sid}"

                elif event_type == "EVALUATE":
                    log_message += " Periodic Evaluation Triggered"

                logs_to_print.append(
                    f"[{current_thread} | Q-Batch: {len(batch):03d}] {log_message}"
                )

            # Single bulk I/O OS call
            if logs_to_print:
                print("\n".join(logs_to_print))

            # Mark all tracked tasks done
            for _ in batch:
                self._log_queue.task_done()
