import numpy as np
import ray
import random
import math
from typing import Dict, Any, Tuple, List, Optional

from flwr.common import (
    FitIns,
    FitRes,
    Parameters,
    parameters_to_ndarrays,
    ndarrays_to_parameters,
)

from flwr.client import Client
from server.server_actor import BaseAsyncServer
from simulation.context import SimulationContext, set_global_context
from simulation.spyker_config import SpykerConfig
from specs.network_metrics import Network
from simulation.network_model import estimate_transmission_time
from client.simulation_client import SimulationFlowerClient
from client.virtual_client import VirtualClient

@ray.remote
class SpykerServer(BaseAsyncServer):
    def __init__(self, 
                 server_id: str,
                 config: SpykerConfig,
                 context: SimulationContext):
        
        set_global_context(context)
        self.context = context 
        try:
            self.self_ref = ray.get_runtime_context().current_actor
        except Exception:
            self.self_ref = None

        super().__init__(server_id)
        
        self.server_id = server_id
        self.config = config

        # --- Machine Learning State ---
        self.global_model_weights: List[np.ndarray] = []
        
        # --- Topology State ---
        self.peer_connections: Dict[str, Network] = {}
        self.next_token_peer: Optional[str] = None
        self.assigned_client_instances: Dict[str, VirtualClient] = {} 

        # --- Spyker Protocol State ---
        self.model_age: int = 0
        self.age_at_last_sync: int = 0

        self.has_token: bool = False
        self.server_ages: Dict[str, int] = {}
        
        # Tracking client activity for Decay function
        self.client_update_counts: Dict[str, int] = {}

        # Self-Reference for scheduling events back to this actor
        self.self_ref = None

    def set_global_context_remote(self, context: SimulationContext):
        """Sets the simulation context for this worker."""
        set_global_context(context)

        self.context = context

    def set_initial_weights(self, weights: List[np.ndarray]):
        """Sets the initial global model."""
        self.global_model_weights = [w.copy() for w in weights]

    def set_topology(self,
                     peer_connections: Dict[str, Network],
                     next_token_peer: str,
                     assigned_clients: List[str]):
        self.peer_connections = peer_connections
        self.next_token_peer = next_token_peer
        self.assigned_clients = assigned_clients

        for peer in peer_connections:
            self.server_ages[peer] = 0

    def register_clients(self, client_objects: Dict[str, SimulationFlowerClient]):
        """
        Wraps the raw SimulationFlowerClient objects in the VirtualClient logic.
        """
        for c_id, inner_client in client_objects.items():
            self.assigned_client_instances[c_id] = VirtualClient(c_id, inner_client)
    
    def set_token_holder(self, is_holder: bool):
        self.has_token = is_holder
    
    # ==============================================================

    def start_simulation(self):
        if not self.global_model_weights:
             raise RuntimeError(f"Server {self.server_id} has no initial weights!")
        
        print(f"[SpykerServer {self.server_id}] Bootstrapping {len(self.assigned_clients)} clients.")
        
        # Starting with token might require a sync from the start
        if self.has_token:
            self._check_synchronization()

        for client_id in self.assigned_client_instances.keys():
            self._schedule_client_task(client_id)

        return self._get_and_clear_events()

    def on_client_update(self, data: Any):
        """
        Handle the completion of a client training task.
        data = {'fit_res': FitRes, 'client_id': str}
        """
        fit_res: FitRes = data['fit_res']
        client_id = data['client_id']
        
        # Extract Weights from Client Result
        client_weights = parameters_to_ndarrays(fit_res.parameters)

        # Calculate Decay (Algorithm 1 SPYKER)
        count = self.client_update_counts.get(client_id, 0) + 1
        self.client_update_counts[client_id] = count
        
        avg_updates = np.mean(list(self.client_update_counts.values())) if self.client_update_counts else 1
        decay_factor = self._calculate_decay(count, avg_updates)

        # Aggregate Client Weights into Global Model
        # Formula: W_global = W_global + decay * (W_client - W_global) SPYKER
        self.global_model_weights = self._aggregate_weights(
            base_weights=self.global_model_weights,
            update_weights=client_weights,
            alpha=decay_factor
        )

        self.model_age += 1

        # Check Sync (Algorithm 2 SPYKER)
        if self.has_token:
            self.server_ages[self.server_id] = self.model_age
            self._check_synchronization()

        self._schedule_client_task(client_id)

    def on_server_message(self, data: Any):
        """Handle Peer-to-Peer Messages."""
        msg_type = data['type']
        sender_id = data['sender_id']

        if msg_type == "MODEL_BROADCAST":
            self._handle_model_broadcast(sender_id, data)
        elif msg_type == "TOKEN":
            self._handle_token_arrival(sender_id, data)

    # =============================================================

    def _aggregate_weights(self, base_weights: List[np.ndarray], update_weights: List[np.ndarray], alpha: float) -> List[np.ndarray]:
        """
        Performs: base + alpha * (update - base)
        """
        new_weights = []
        for w_base, w_upd in zip(base_weights, update_weights):
            diff = w_upd - w_base
            new_w = w_base + (alpha * diff)
            new_weights.append(new_w)
        return new_weights

    def _calculate_decay(self, client_updates, avg_updates):
        """Spyker Algorithm 1: Learning Rate Decay."""
        if client_updates < avg_updates:
            return 1.0

        # exp-decay for very active clients
        val = math.exp(-self.config.decay_beta * (client_updates - avg_updates))
        return max(self.config.min_learning_rate, val)
    
    def _get_model_size_mb(self) -> float:
        """Calculates the size of the current global model in Megabytes."""
        if not self.global_model_weights:
            return 0.001 # Fallback for empty init
        
        total_bytes = sum(w.nbytes for w in self.global_model_weights)
        return total_bytes / (1024.0 * 1024.0)

    def _check_synchronization(self):
        """Spyker Algorithm 2: Server Sync Decision."""
        if not self.has_token:
            return
        
        min_age = min(self.server_ages.values()) if self.server_ages else 0
        max_age = max(self.server_ages.values()) if self.server_ages else 0

        inter_drift = max_age - min_age
        intra_drift = self.model_age - self.age_at_last_sync

        if inter_drift >= self.config.h_inter or intra_drift >= self.config.h_intra:
            # Broadcast to all other servers
            self.age_at_last_sync = self.model_age
            self._broadcast_model_to_all()
        else:
            self._pass_token()
    
    def _broadcast_model_to_all(self):
        weights_ref = ray.put(self.global_model_weights)
        
        for peer_id in self.peer_connections.keys():
            self._send_server_message(
                target_id = peer_id,
                msg_type = "MODEL_BROADCAST",
                payload = {
                    "weights_ref": weights_ref,
                    "age": self.model_age
                }
            )
        
        # After broadcasting, we pass the token
        self._pass_token()

    def _handle_model_broadcast(self, sender_id, payload):
        sender_age = payload['age']
        weights_ref = payload['weights_ref']
        
        # Fetch the actual numpy arrays from Ray Object Store
        peer_weights = ray.get(weights_ref)

        # Update knowledge
        self.server_ages[sender_id] = sender_age

        # Calculate Sigmoid Weight
        delta_age = sender_age - self.model_age
        sigmoid_w = 1.0 / (1.0 + math.exp(-self.config.sigmoid_phi * (delta_age)))

        # Aggregation as in SPYKER: W = W + eta_server * sigmoid * (W_peer - W)
        effective_alpha = self.config.server_learning_rate * sigmoid_w
        
        self.global_model_weights = self._aggregate_weights(
            base_weights=self.global_model_weights,
            update_weights=peer_weights,
            alpha=effective_alpha
        )
        
        # Update local age
        self.model_age = max(self.model_age, sender_age)

    def _handle_token_arrival(self, sender_id, payload):
        self.has_token = True

        token_ages = payload.get("server_ages", {})
        # Merge the token's knowledge with local knowledge
        for s_id, age in token_ages.items():
            self.server_ages[s_id] = max(self.server_ages.get(s_id, 0), age)

        self.server_ages[self.server_id] = self.model_age

        self._check_synchronization()

    def _pass_token(self):
        if not self.next_token_peer:
            return # single server setup
        
        self.has_token = False

        self._send_server_message(
            target_id = self.next_token_peer,
            msg_type = "TOKEN",
            payload = {
                "server_ages": self.server_ages.copy()
            }
        )

    # =====================================================================

    def _schedule_client_task(self, client_id):
        """
        Interacts with the VirtualClient to perform training and simulation.
        """
        config = {
            "server_id": self.server_id,
            "epochs": 1, # TODO:parametrize and pass from frontend
            "model_complexity": 1.0,
            "model_age": self.model_age
        }
        
        fit_ins = FitIns(
            parameters=ndarrays_to_parameters(self.global_model_weights),
            config=config
        )
        
        client_instance = self.assigned_client_instances[client_id]
        fit_res = client_instance.fit(fit_ins)
        
        sim_duration = fit_res.metrics["simulation_duration"]
        
        target_ref = self.self_ref if self.self_ref else ray.get_runtime_context().current_actor

        self._schedule_event(
            delay = sim_duration,
            target_actor = target_ref, 
            event_type = "CLIENT_UPDATE",
            data = {
                "client_id": client_id,
                "fit_res": fit_res
            }
        )

    def _send_server_message(self, target_id: str, msg_type: str, payload: Any):
        """
        Calculates network delay for Server-to-Server comms and schedules the event.
        """
        sender_spec = self.context.get_server_spec(self.server_id)
        receiver_spec = self.context.get_server_spec(target_id)

        if msg_type == "MODEL_BROADCAST":
            payload_size_mb = self._get_model_size_mb()
        else:
            # Estimate for Tokens as 1KB
            payload_size_mb = 0.001

        delay = estimate_transmission_time(
            sender_spec=sender_spec,
            receiver_spec=receiver_spec,
            network_metrics=sender_spec.network_metrics,
            metrics_id=target_id,                        
            payload_size_mb=payload_size_mb
        )

        payload['sender_id'] = self.server_id
        payload['type'] = msg_type

        target_actor = self.context.server_actor_handles[target_id]

        self._schedule_event(
            delay=delay,
            target_actor=target_actor,
            event_type="SERVER_MESSAGE",
            data=payload
        )
