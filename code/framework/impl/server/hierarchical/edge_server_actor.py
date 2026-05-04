import ray
from strategies.server_strategies import get_sync_server_strategy
import torch
import numpy as np
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
from simulation.network_model import estimate_transmission_time
from simulation.context import SimulationContext, set_global_context
from specs.server_spec import ServerSpec
from client.virtual_client import VirtualClientActor

CLIENT_UPDATE = "CLIENT_UPDATE"
MODEL_SYNC = "MODEL_SYNC"
SERVER_MESSAGE = "SERVER_MESSAGE"


@ray.remote
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

        self.assigned_client_instances: Dict[str, VirtualClientActor] = {}

        # Buffer stores: {client_id: (weights, num_examples)}
        self.client_updates_buffer: Dict[str, Tuple[List[np.ndarray], int]] = {}
        self.model_age = 0
        self.training_config: Dict[str, Scalar] = {}

        self.aggregation_strategy = get_sync_server_strategy("fedavg")

        try:
            self.self_ref = ray.get_runtime_context().current_actor
        except Exception:
            self.self_ref = None

    def set_global_context_remote(self, context: SimulationContext):
        simulation.context.set_global_context(context)
        self.context = context

    def register_clients(self, client_configs: Dict[str, Dict[str, Any]]):
        """Instantiates PyTorch DataLoaders safely inside the Ray worker."""
        gpu_fraction = 0
        for c_id, config in client_configs.items():
            actor = VirtualClientActor.options(
                num_cpus=1e-4, num_gpus=gpu_fraction
            ).remote(client_id=c_id, client_config=config, context=self.context)
            self.assigned_client_instances[c_id] = actor

    def set_orchestrator(self, orchestrator_ref):
        super().set_orchestrator(orchestrator_ref)
        for client_actor in self.assigned_client_instances.values():
            client_actor.set_orchestrator.remote(orchestrator_ref)

    def start_simulation(self):
        raise NotImplementedError(
            "The Simulation can only be started through a Super Server, not an Edge Server."
        )

    def on_server_message(self, data: Dict[str, Any], direct_refs: Any = None):
        event_type = data.get("type")

        if event_type == "MODEL_SYNC":
            # Native extraction of ref to avoid memory bottleneck
            self.global_model_weights = direct_refs
            self.model_age = data["model_age"]
            self.training_config = data["training_config"]

            global_params = ndarrays_to_parameters(self.global_model_weights)
            local_config = self.training_config.copy()
            local_config["server_id"] = self.server_id
            local_config["model_age"] = self.model_age
            target_ref = (
                self.self_ref
                if self.self_ref
                else ray.get_runtime_context().current_actor
            )

            weights_ref = ray.put(self.global_model_weights)

            for (
                client_id,
                virtual_client_actor,
            ) in self.assigned_client_instances.items():
                self._schedule_event(
                    delay=0.0,
                    target_actor=virtual_client_actor,
                    event_type="START_FIT",
                    data={
                        "config": local_config,
                        "server_id": self.server_id,
                        "server_ref": target_ref,
                    },
                    refs=weights_ref,
                )
        else:
            raise ValueError(
                f"[Edge Server {self.server_id}] Unknown event type: {event_type}"
            )

    def on_client_update(self, data: Dict[str, Any], direct_refs: Any = None):
        client_id = data["client_id"]
        num_examples = data["num_examples"]

        weights = direct_refs

        self.client_updates_buffer[client_id] = (weights, num_examples)

        if len(self.client_updates_buffer) >= self.min_clients_per_round:
            self._aggregate_and_send_upstream()

    def _aggregate_and_send_upstream(self):
        """
        Aggregates local buffer and sends result to Super Server.
        """
        updates_list = list(self.client_updates_buffer.values())
        total_samples = sum(n for _, n in updates_list)

        if total_samples == 0:
            print(f"[Edge {self.server_id}] Warning: 0 samples aggregated.")
            return

        aggregated_weights = self.aggregation_strategy.aggregate(
            global_weights=self.global_model_weights,
            updates=updates_list
        )

        # Optimize cross-node transfer
        weights_ref = ray.put(aggregated_weights)

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
            event_type="SERVER_MESSAGE",
            data={
                "type": "AGGREGATION_SYNC",
                "edge_server_id": self.server_id,
                "num_samples": total_samples,
            },
            refs=weights_ref,
        )
        self.client_updates_buffer.clear()
