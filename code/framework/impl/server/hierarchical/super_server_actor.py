import ray
import numpy as np
from typing import List, Dict, Any, Tuple

from server.server_actor import BaseAsyncServer
from simulation.network_model import estimate_transmission_time
from simulation.context import SimulationContext, set_global_context

SERVER_MESSAGE = "SERVER_MESSAGE"


@ray.remote
class SuperServer(BaseAsyncServer):
    def __init__(
        self,
        server_id: str,
        initial_parameters: List[np.ndarray],
        required_updates: int,
        training_config: Dict[str, Any],
        context: SimulationContext,
    ):
        set_global_context(context)

        super().__init__(server_id)

        self.initial_parameters = initial_parameters
        self.edge_server_refs = {}
        self.required_updates = required_updates
        self.training_config = training_config

        self.updates_buffer: Dict[str, Tuple[List[np.ndarray], int]] = {}
        self.model_age = 0

        self.global_model_weights = self.initial_parameters

    def set_edge_servers(self, edge_server_refs: Dict[str, ray.ObjectRef]):
        """
        Late-binding of Edge Servers to avoid circular dependency.
        """
        self.edge_server_refs = edge_server_refs
        print(f"[SuperServer] Registered {len(edge_server_refs)} edge servers.")

    def get_metrics(self) -> Dict[str, Any]:
        return {
            "model_age": self.model_age,
            "pending_updates": len(self.updates_buffer),
        }

    def start_simulation(self):
        """
        Kickstart the simulation by sending the Initial Model (Age 0)
        to all Edge Servers.
        """
        self._broadcast_global_model()

        return self._get_and_clear_events()

    def on_client_update(self, _):
        raise NotImplementedError(
            "A Super Server should never receive a direct update from a Virtual Client."
        )

    def on_server_message(self, data: Dict[str, Any], direct_refs: Any = None):
        """
        Receive partial global models from Edge Servers.
        Payload: { "edge_server_id": str, "weights": List[np.ndarray], "num_samples": int }
        """
        msg_type = data.get("type")

        if msg_type == "AGGREGATION_SYNC":
            edge_server_id = data["edge_server_id"]
            weights = direct_refs
            num_samples = data["num_samples"]

            self.updates_buffer[edge_server_id] = (weights, num_samples)

            if len(self.updates_buffer) >= self.required_updates:
                # --- FedAvg Logic ---
                total_samples = 0
                weighted_sum = [np.zeros_like(w) for w in self.initial_parameters]
                for w, n in self.updates_buffer.values():
                    total_samples += n
                    for i in range(len(w)):
                        weighted_sum[i] += w[i] * n
                # --------------------

                if total_samples > 0:
                    self.global_model_weights = [
                        ws / total_samples for ws in weighted_sum
                    ]
                else:
                    print(
                        f"[SuperServer] Warning: Total samples was 0 in round {self.model_age}"
                    )

                self.updates_buffer.clear()
                self.model_age += 1

                self._broadcast_global_model()

    def _broadcast_global_model(self):
        """Helper to send the current global model to all Edge Servers."""

        super_spec = self.context.get_server_spec(self.server_id)
        weights_ref = ray.put(self.global_model_weights)

        for edge_server_id, edge_server_ref in self.edge_server_refs.items():
            edge_spec = self.context.get_server_spec(edge_server_id)

            total_bytes = sum(w.nbytes for w in self.global_model_weights)
            model_size_mb = total_bytes / (1024 * 1024)
            latency = estimate_transmission_time(
                sender_spec=super_spec,
                receiver_spec=edge_spec,
                network_metrics=edge_spec.network_metrics,
                metrics_id=self.server_id,
                payload_size_mb=model_size_mb,
            )

            self._schedule_event(
                delay=latency,
                target_actor=edge_server_ref,
                event_type="SERVER_MESSAGE",
                data={
                    "type": "MODEL_SYNC",
                    "model_age": self.model_age,
                    "training_config": self.training_config,
                },
                refs=weights_ref,
            )
