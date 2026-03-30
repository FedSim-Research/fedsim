import ray
import numpy as np
import yaml
import simulation.context
from typing import List, Dict, Tuple, Any

from flwr.common import (
    FitIns,
    FitRes,
    Scalar,
    ndarrays_to_parameters,
    parameters_to_ndarrays,
)

from flwr.client import Client

from server.server_actor import BaseAsyncServer
from client.simulation_client import SimulationFlowerClient
from client.virtual_client import VirtualClient
from simulation.network_model import estimate_transmission_time
from simulation.context import SimulationContext, set_global_context
from specs.server_spec import ServerSpec

CLIENT_UPDATE = "CLIENT_UPDATE"
MODEL_SYNC = "MODEL_SYNC"
SERVER_MESSAGE = "SERVER_MESSAGE"


with open("config.yaml", "r") as config_file:
    global doc
    doc = yaml.load(config_file, Loader=yaml.SafeLoader)


@ray.remote(num_gpus=doc["num_gpus"])
class EdgeServer(BaseAsyncServer):
    def __init__(
        self,
        server_id: str,
        super_server_id: str,
        super_server_ref: ray.ObjectRef,
        min_clients_per_round: int,
        context: SimulationContext,
    ):
        set_global_context(context)

        super().__init__(server_id)

        self.server_id = server_id
        self.super_server_id = super_server_id
        self.super_server_ref = super_server_ref
        self.min_clients_per_round = min_clients_per_round

        self.assigned_client_instances: Dict[str, VirtualClient] = {}

        # Buffer stores: {client_id: (weights, num_examples)}
        self.client_updates_buffer: Dict[str, Tuple[List[np.ndarray], int]] = {}
        self.model_age = 0
        self.training_config: Dict[str, Scalar] = {}

        try:
            self.self_ref = ray.get_runtime_context().current_actor
        except Exception:
            self.self_ref = None

    def set_global_context_remote(self, context: SimulationContext):
        simulation.context.set_global_context(context)
        self.context = context

    def register_clients(self, client_configs: Dict[str, Dict[str, Any]]):
        """Instantiates PyTorch DataLoaders safely inside the Ray worker."""
        for c_id, config in client_configs.items():
            inner_client = SimulationFlowerClient(
                partition_id=config["dataset_partition_id"],
                num_partitions=config["total_partitions"],
                seed=config.get("seed")
            )
            self.assigned_client_instances[c_id] = VirtualClient(c_id, inner_client)

    def start_simulation(self):
        raise NotImplementedError(
            "The Simulation can only be started through a Super Server, not an Edge Server."
        )

    def on_server_message(self, data: Dict[str, Any]):
        """
        Handle Global Model coming from Super Server.
        """
        event_type = data.get("type")

        print(
            f"[{self.server_id}] Received {event_type}. Assigned Clients: {len(self.assigned_client_instances)}"
        )

        if event_type == MODEL_SYNC:
            self.global_model_weights = data["weights"]
            self.model_age = data["model_age"]
            self.training_config = data["training_config"]

            global_params = ndarrays_to_parameters(self.global_model_weights)

            local_config = self.training_config.copy()
            local_config["server_id"] = self.server_id
            local_config["model_age"] = self.model_age

            # DEBUG PRINT
            if not self.assigned_client_instances:
                print(
                    f"[{self.server_id}] ERROR: No clients assigned! Loop will not run."
                )

            for client_id, virtual_client in self.assigned_client_instances.items():
                try:
                    fit_ins = FitIns(global_params, local_config)
                    fit_res: FitRes = virtual_client.fit(fit_ins)

                    target_ref = self.self_ref if self.self_ref else ray.get_runtime_context().current_actor

                    self._schedule_event(
                        delay=fit_res.metrics["simulation_duration"],
                        target_actor=target_ref,
                        event_type=CLIENT_UPDATE,
                        data={
                            "client_id": client_id,
                            "server_id": self.server_id,
                            "fit_res": fit_res
                        },
                    )

                    duration = fit_res.metrics["simulation_duration"]
                    print(f"[{self.server_id}] Client {client_id} finished. Duration: {duration:.2f} seconds")

                except Exception as e:
                    import traceback
                    print(f"[{self.server_id}] CRASH PROCESSING CLIENT {client_id}: {e}")
                    print(traceback.format_exc())
                    
        else:
            raise ValueError(f"[Edge Server {self.server_id}] Unknown event type: {event_type}")

    def on_client_update(self, data: Dict[str, Any]):
        """
        Handle a VirtualClient finishing training.
        """
        fit_res = data["fit_res"]
        client_id = data["client_id"]
        num_examples = fit_res.num_examples

        weights = parameters_to_ndarrays(fit_res.parameters)

        self.client_updates_buffer[client_id] = (weights, num_examples)

        if len(self.client_updates_buffer) >= self.min_clients_per_round:
            self._aggregate_and_send_upstream()

    def _aggregate_and_send_upstream(self):
        """
        Aggregates local buffer and sends result to Super Server.
        """
        # --- FedAvg Logic ---
        total_samples = 0
        weighted_sum = [np.zeros_like(w) for w in self.global_model_weights]

        for w, n in self.client_updates_buffer.values():
            total_samples += n
            for i in range(len(w)):
                weighted_sum[i] += w[i] * n
        # --------------------

        if total_samples == 0:
            print(f"[Edge {self.server_id}] Warning: 0 samples aggregated.")
            return

        aggregated_weights = [ws / total_samples for ws in weighted_sum]

        edge_server_spec = self.context.get_server_spec(self.server_id)
        super_server_spec = self.context.get_server_spec(self.super_server_id)

        total_bytes = sum(w.nbytes for w in aggregated_weights)
        payload_size_mb = total_bytes / (1024 * 1024)

        delay = estimate_transmission_time(
            sender_spec=edge_server_spec,
            receiver_spec=super_server_spec,
            network_metrics=edge_server_spec.network_metrics,
            metrics_id=self.super_server_id,
            payload_size_mb=payload_size_mb,
        )

        self._schedule_event(
            delay=delay,
            target_actor=self.super_server_ref,
            event_type=SERVER_MESSAGE,
            data={
                "edge_server_id": self.server_id,
                "weights": aggregated_weights,
                "num_samples": total_samples,
            },
        )

        self.client_updates_buffer.clear()
