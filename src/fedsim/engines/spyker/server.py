import math
from collections import OrderedDict
from typing import Any, Dict, List, Optional

import numpy as np
import ray

from fedsim.clients.actor import VirtualClientActor
from fedsim.engines.base import BaseAsyncServer
from fedsim.simulation.context import SimulationContext, set_global_context
from fedsim.simulation.network_model import estimate_transmission_time
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.network_metrics import Network
from fedsim.strategies.server_strategies import get_async_server_strategy

TOKEN_PAYLOAD_BYTES = 1000


@ray.remote(num_cpus=0, num_gpus=0)
class SpykerServer(BaseAsyncServer):
    def __init__(self, server_id: str, config: FullConfiguration, context: SimulationContext):
        set_global_context(context)
        self.context = context
        try:
            self.self_ref = ray.get_runtime_context().current_actor
        except Exception:
            self.self_ref = None

        super().__init__(server_id)

        self.server_id = server_id
        self.full_config = config
        self.spyker_config = config.spyker

        # --- Machine Learning State ---
        self.global_model_weights: List[np.ndarray] = []

        # --- Topology State ---
        self.peer_connections: Dict[str, Network] = {}
        self.next_token_peer: Optional[str] = None
        self.assigned_client_instances: Dict[str, VirtualClientActor] = {}

        # --- Spyker Protocol State ---
        self.model_age: int = 0
        self.age_at_last_sync: int = 0

        self.has_token: bool = False
        self.server_ages: Dict[str, int] = {}

        self.client_learning_rates: Dict[str, float] = {}

        # Tracking client activity for Decay function
        self.client_update_counts: Dict[str, int] = {}
        self.total_client_updates_processed = 0

        # Self-Reference for scheduling events back to this actor
        self.self_ref = None

        # A round includes our own broadcast and one contribution per peer.
        self._sync_participants: OrderedDict[str, set[str]] = OrderedDict()
        self._sync_sequence = 0
        self._sync_rounds_completed = 0
        self._peer_models_aggregated = 0
        self.MAX_BROADCAST_CACHE = 1000

        self._cached_global_weights_ref = None

        # The current broadcast ID
        self.current_bid: str = ""
        self.ongoing_sync: bool = False
        self.total_servers = 0

        self.aggregation_strategy = get_async_server_strategy("spyker")

    def set_global_context_remote(self, context: SimulationContext):
        """Sets the simulation context for this worker."""
        set_global_context(context)

        self.context = context

    def set_initial_weights(self, weights: List[np.ndarray]):
        """Sets the initial global model."""
        self.global_model_weights = [w.copy() for w in weights]

    def set_topology(
        self,
        peer_connections: Dict[str, Network],
        next_token_peer: str | None,
        assigned_clients: List[str],
    ):
        self.peer_connections = {
            peer: network for peer, network in peer_connections.items() if peer != self.server_id
        }
        self.next_token_peer = next_token_peer
        self.assigned_clients = assigned_clients
        self.total_servers = len(self.peer_connections) + 1
        print(f"[{self.server_id}] Total Servers set to {self.total_servers}")

        for peer in self.peer_connections:
            self.server_ages[peer] = 0
        self.server_ages[self.server_id] = 0

    def register_clients(self, client_configs: Dict[str, Any]):
        """Spawns Client Actors dynamically to process tasks concurrently."""
        for c_id, config in client_configs.items():
            actor = VirtualClientActor.remote(
                client_id=c_id, client_config=config, context=self.context
            )
            self.assigned_client_instances[c_id] = actor

    def set_orchestrator(self, orchestrator_ref):
        super().set_orchestrator(orchestrator_ref)
        # Link clients to orchestrator
        for client_actor in self.assigned_client_instances.values():
            client_actor.set_orchestrator.remote(orchestrator_ref)

    def set_token_holder(self, is_holder: bool):
        self.has_token = is_holder

    def get_metrics(self) -> Dict[str, Any]:
        """Returns Spyker specific metrics for telemetry."""
        return {
            "model_age": self.model_age,
            "total_client_updates": sum(self.client_update_counts.values()),
            "has_token": int(self.has_token),
            "sync_rounds_initiated": self._sync_sequence,
            "sync_rounds_completed": self._sync_rounds_completed,
            "peer_models_aggregated": self._peer_models_aggregated,
        }

    # ==============================================================

    def start_simulation(self):
        if not self.global_model_weights:
            raise RuntimeError(f"Server {self.server_id} has no initial weights!")

        print(
            f"[SpykerServer {self.server_id}] Bootstrapping {len(self.assigned_clients)} clients."
        )

        # Starting with token might require a sync from the start
        if self.has_token:
            self._check_synchronization()

        for client_id in self.assigned_client_instances.keys():
            self._schedule_client_task(client_id)

        return self._get_and_clear_events()

    def on_client_update(self, data: Any, direct_refs: Any = None):
        """
        Handle the completion of a client training task.
        data = {'fit_res': FitRes, 'client_id': str}
        """
        client_id = data["client_id"]

        # Extract Weights from Client Result
        client_weights = direct_refs

        # Model age the client trained on
        metrics = data.get("metrics", {})
        ref_model_age = metrics.get("ref_model_age", self.model_age)

        # Staleness Dampener
        age_drift = self.model_age - ref_model_age
        staleness_weight = 1.0 / (1.0 + max(0, age_drift))

        # Aggregate Client weights into global model
        eta_server = self.spyker_config.server_learning_rate
        effective_alpha = eta_server * staleness_weight

        self.global_model_weights = self.aggregation_strategy.aggregate(
            global_weights=self.global_model_weights,
            update_weights=client_weights,
            alpha=effective_alpha,
        )

        # Invalidate global weights cache because of recent change
        self._cached_global_weights_ref = None

        self.model_age += 1

        self.total_client_updates_processed += 1
        count = self.client_update_counts.get(client_id, 0) + 1
        self.client_update_counts[client_id] = count

        num_active_clients = len(self.client_update_counts)
        avg_updates = self.total_client_updates_processed / num_active_clients

        base_client_lr = self.full_config.training.learning_rate
        new_client_lr = self._calculate_decay(count, avg_updates, base_client_lr)
        self.client_learning_rates[client_id] = new_client_lr

        # Check Sync (Algorithm 2 SPYKER)
        if self.has_token:
            self.server_ages[self.server_id] = self.model_age
            self._check_synchronization()

        self._schedule_client_task(client_id)

    def on_server_message(self, data: Any, direct_refs: Any = None):
        msg_type = data["type"]
        sender_id = data["sender_id"]

        if msg_type == "MODEL_BROADCAST":
            self._handle_model_broadcast(sender_id, data, direct_refs)
        elif msg_type == "TOKEN":
            self._handle_token_arrival(sender_id, data)

    # =============================================================

    def _calculate_decay(self, client_updates, avg_updates, base_lr):
        """Spyker Algorithm 1: Learning Rate Decay."""
        if client_updates < avg_updates:
            return base_lr

        # linear decay for active clients
        decayed_lr = base_lr - (self.spyker_config.decay_beta * (client_updates - avg_updates))
        return max(self.spyker_config.min_learning_rate, decayed_lr)

    def _get_model_size_bytes(self) -> int:
        """Count tensor payload bytes, excluding transport and message metadata."""
        return sum(w.nbytes for w in self.global_model_weights)

    def _check_synchronization(self):
        """Spyker Algorithm 2: Server Sync Decision."""
        if not self.has_token or self.ongoing_sync or not self.peer_connections:
            return

        min_age = min(self.server_ages.values()) if self.server_ages else 0
        max_age = max(self.server_ages.values()) if self.server_ages else 0

        inter_drift = max_age - min_age
        intra_drift = self.model_age - self.age_at_last_sync

        if inter_drift >= self.spyker_config.h_inter:
            reason = f"Inter-Drift {inter_drift} >= {self.spyker_config.h_inter}"
            self._broadcast_model_to_all(reason)
        elif intra_drift >= self.spyker_config.h_intra:
            reason = f"Intra-Drift {intra_drift} >= {self.spyker_config.h_intra}"
            self._broadcast_model_to_all(reason)
        else:
            self._pass_token()

    def _broadcast_model_to_all(self, reason="Unknown"):
        if self.ongoing_sync or not self.peer_connections:
            return

        self.ongoing_sync = True
        self.age_at_last_sync = self.model_age
        self._sync_sequence += 1
        bid = f"{self.server_id}_{self._sync_sequence}"
        self.current_bid = bid
        self._remember_sync(bid)

        print(f"[{self.server_id}] Initiating SYNC {bid}. Reason: {reason}")

        self._perform_broadcast(bid)

    def _remember_sync(self, bid):
        participants = {self.server_id}
        self._sync_participants[bid] = participants
        if len(self._sync_participants) > self.MAX_BROADCAST_CACHE:
            expired = next(key for key in self._sync_participants if key != self.current_bid)
            del self._sync_participants[expired]
        return participants

    def _handle_model_broadcast(self, sender_id, payload, direct_refs):
        if sender_id == self.server_id or sender_id not in self.peer_connections:
            return

        bid = payload["bid"]
        sender_age = payload["age"]
        self.server_ages[sender_id] = max(self.server_ages.get(sender_id, 0), sender_age)

        participants = self._sync_participants.get(bid)
        if participants is None:
            participants = self._remember_sync(bid)
            self.age_at_last_sync = self.model_age
            # Publish the pre-aggregation snapshot once, as in Spyker Algorithm 2.
            self._perform_broadcast(bid)
        if sender_id in participants:
            return
        participants.add(sender_id)

        # --- Peer Weight Aggregations ---
        peer_weights = direct_refs

        # Calculate Sigmoid Weight
        delta_age = sender_age - self.model_age
        denominator = max(1, self.model_age)
        a_val = (self.spyker_config.sigmoid_phi * delta_age) / denominator
        sigmoid_w = 1.0 / (1.0 + math.exp(-a_val))

        # Aggregation as in SPYKER: W = W + eta_server * sigmoid * (W_peer - W)
        effective_alpha = self.spyker_config.server_learning_rate * sigmoid_w

        self.global_model_weights = self.aggregation_strategy.aggregate(
            global_weights=self.global_model_weights,
            update_weights=peer_weights,
            alpha=effective_alpha,
        )

        # Invalidate global weights cache because of recent change
        self._cached_global_weights_ref = None

        # Update local age
        old_age = self.model_age
        weighted_age = (1.0 - effective_alpha) * self.model_age + (effective_alpha * sender_age)
        self.model_age = int(round(weighted_age))

        self.model_age = max(old_age, self.model_age)
        self.server_ages[self.server_id] = self.model_age

        self._peer_models_aggregated += 1
        if len(participants) == self.total_servers:
            self._sync_rounds_completed += 1

        if self.model_age > old_age:
            print(
                f"[{self.server_id}] Aggregated model from {sender_id}. Age jumped {old_age} -> {self.model_age}"
            )

        if self.has_token and bid == self.current_bid and len(participants) == self.total_servers:
            print(f"[{self.server_id}] Sync {bid} Complete. Releasing Token.")
            self.current_bid = ""
            self.ongoing_sync = False
            self._pass_token(immediate_sync_after_release=True)

    def _handle_token_arrival(self, sender_id, payload):
        self.has_token = True

        token_ages = payload.get("server_ages", {})
        # Merge the token's knowledge with local knowledge
        for s_id, age in token_ages.items():
            self.server_ages[s_id] = max(self.server_ages.get(s_id, 0), age)

        self.server_ages[self.server_id] = self.model_age

        self._check_synchronization()

    def _pass_token(self, immediate_sync_after_release: bool = False):
        if not self.next_token_peer or self.next_token_peer == self.server_id:
            return  # single server setup

        self.has_token = False

        token_processing_delay = (
            0.0 if immediate_sync_after_release else self.full_config.simulation.idle_token_delay
        )

        self._send_server_message(
            target_id=self.next_token_peer,
            msg_type="TOKEN",
            payload={"server_ages": self.server_ages.copy()},
            added_delay=token_processing_delay,
        )

    def _perform_broadcast(self, bid):
        # Put large object into Plasma store once
        if self._cached_global_weights_ref is None:
            self._cached_global_weights_ref = ray.put(self.global_model_weights)

        for peer_id in self.peer_connections.keys():
            self._send_server_message(
                target_id=peer_id,
                msg_type="MODEL_BROADCAST",
                payload={"age": self.model_age, "bid": bid},
                refs=self._cached_global_weights_ref,  # Pass ref so Orchestrator can utilize Ray's implicit fetching
            )

    # =====================================================================

    def _schedule_client_task(self, client_id):
        train_config = self.full_config.training

        client_lr = self.client_learning_rates.get(client_id, train_config.learning_rate)

        config = {
            "server_id": self.server_id,
            "epochs": train_config.local_epochs,
            "batch_size": train_config.batch_size,
            "lr": client_lr,
            "model_complexity": train_config.model_complexity,
            "model_age": self.model_age,
        }

        client_actor = self.assigned_client_instances[client_id]
        target_ref = self.self_ref if self.self_ref else ray.get_runtime_context().current_actor

        if self._cached_global_weights_ref is None:
            self._cached_global_weights_ref = ray.put(self.global_model_weights)

        self._schedule_event(
            delay=0.0,
            target_actor=client_actor,
            event_type="START_FIT",
            data={
                "config": config,
                "server_id": self.server_id,
                "server_ref": target_ref,
            },
            refs=self._cached_global_weights_ref,
        )

    def _send_server_message(
        self,
        target_id: str,
        msg_type: str,
        payload: Any,
        added_delay: float = 0.0,
        refs: Any = None,
    ):
        """
        Calculates network delay for Server-to-Server comms and schedules the event.
        """
        sender_spec = self.context.get_server_spec(self.server_id)
        receiver_spec = self.context.get_server_spec(target_id)

        if msg_type == "MODEL_BROADCAST":
            payload_size_bytes = self._get_model_size_bytes()
        else:
            # Control messages use an estimated 1 kB payload (decimal bytes).
            payload_size_bytes = TOKEN_PAYLOAD_BYTES

        delay = estimate_transmission_time(
            sender_spec=sender_spec,
            receiver_spec=receiver_spec,
            network_metrics=sender_spec.network_metrics,
            metrics_id=target_id,
            payload_size_bytes=payload_size_bytes,
            rng=self.random_streams.stream("network", target_id),
        )

        final_delay = delay + added_delay

        payload["sender_id"] = self.server_id
        payload["type"] = msg_type

        target_actor = self.context.server_actor_handles[target_id]

        self._schedule_event(
            delay=final_delay,
            target_actor=target_actor,
            event_type="SERVER_MESSAGE",
            data=payload,
            refs=refs,
        )
