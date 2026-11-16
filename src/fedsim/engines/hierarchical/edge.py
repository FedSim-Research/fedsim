from typing import Any, Dict, List, Tuple

import numpy as np
import ray

import fedsim.simulation.context
from fedsim.clients.handle import ClientHandle
from fedsim.engines.base import BaseAsyncServer
from fedsim.simulation.context import SimulationContext, set_global_context
from fedsim.simulation.network_model import estimate_transmission_time
from fedsim.strategies.server_strategies import get_sync_server_strategy

CLIENT_UPDATE = "CLIENT_UPDATE"
MODEL_SYNC = "MODEL_SYNC"
SERVER_MESSAGE = "SERVER_MESSAGE"


@ray.remote(num_cpus=0, num_gpus=0)
class EdgeServer(BaseAsyncServer):
    def __init__(
        self,
        server_id: str,
        super_server_id: str,
        super_server_ref: ray.ObjectRef,
        min_clients_per_round: int,
        context: SimulationContext,
        edge_rounds: int = 1,
    ):
        set_global_context(context)

        super().__init__(server_id)

        self.server_id = server_id
        self.super_server_id = super_server_id
        self.super_server_ref = super_server_ref
        self.min_clients_per_round = min_clients_per_round
        self.edge_rounds = edge_rounds
        self.edge_rounds_done = 0

        self.assigned_client_instances: Dict[str, ClientHandle] = {}

        # Buffer stores: {client_id: (weights, num_examples)}
        self.client_updates_buffer: Dict[str, Tuple[List[np.ndarray], int]] = {}
        self.model_age = 0
        self.training_config: Dict[str, Any] = {}

        self.aggregation_strategy = get_sync_server_strategy("fedavg")

        try:
            self.self_ref = ray.get_runtime_context().current_actor
        except Exception:
            self.self_ref = None

    def set_global_context_remote(self, context: SimulationContext):
        fedsim.simulation.context.set_global_context(context)
        self.context = context

    def register_clients(self, client_configs: Dict[str, Dict[str, Any]]):
        """Register logical clients without creating one process per client."""
        context_ref = ray.put(self.context)
        for c_id, config in client_configs.items():
            actor = ClientHandle(
                execution_id=self.context.execution_id,
                client_id=c_id,
                client_config=dict(config),
                context_ref=context_ref,
            )
            self.assigned_client_instances[c_id] = actor

    def set_orchestrator(self, orchestrator_ref):
        super().set_orchestrator(orchestrator_ref)

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
            self.edge_rounds_done = 0
            self._dispatch_clients()
        else:
            raise ValueError(f"[Edge Server {self.server_id}] Unknown event type: {event_type}")

    def _dispatch_clients(self):
        """Send START_FIT with the current edge model to all assigned clients."""
        local_config = self.training_config.copy()
        local_config["server_id"] = self.server_id
        local_config["model_age"] = self.model_age
        target_ref = self.self_ref if self.self_ref else ray.get_runtime_context().current_actor

        weights_ref = ray.put(self.global_model_weights)

        for virtual_client_actor in self.assigned_client_instances.values():
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
            global_weights=self.global_model_weights, updates=updates_list
        )
        self.client_updates_buffer.clear()

        # HierFAVG (Liu et al. 2020): repeat edge rounds before reporting upstream.
        self.edge_rounds_done += 1
        if self.edge_rounds_done < self.edge_rounds:
            self.global_model_weights = aggregated_weights
            self._dispatch_clients()
            return
        self.edge_rounds_done = 0

        # Optimize cross-node transfer
        weights_ref = ray.put(aggregated_weights)

        edge_server_spec = self.context.get_server_spec(self.server_id)
        super_server_spec = self.context.get_server_spec(self.super_server_id)

        total_bytes = sum(w.nbytes for w in aggregated_weights)

        delay = estimate_transmission_time(
            sender_spec=edge_server_spec,
            receiver_spec=super_server_spec,
            network_metrics=edge_server_spec.network_metrics,
            metrics_id=self.super_server_id,
            payload_size_bytes=total_bytes,
            rng=self.random_streams.stream("network", self.super_server_id),
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
