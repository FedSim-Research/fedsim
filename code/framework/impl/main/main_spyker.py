from collections import OrderedDict
from typing import Dict, List, Any, Tuple

import ray
import torch
from torch.utils.data import DataLoader
from torchvision.datasets import CIFAR10
from torchvision.transforms import Compose, Normalize, ToTensor
from flwr.common import parameters_to_ndarrays

from main.task import Net, test
from simulation.context import SimulationContext, set_global_context
from simulation.orchestrator import SimulationOrchestrator
from simulation.spyker_config import FullConfiguration
from specs.server_spec import ServerSpec
from specs.client_spec import ClientSpec
from specs.network_metrics import Network
from specs.performance_metrics import Performance
from server.spyker.spyker_server_actor import SpykerServer
from client.simulation_client import SimulationFlowerClient

SIM_NAME = "Spyker_CIFAR10"

class DataLoaderAdapter:
    """Wraps DataLoader for Flower compatibility (Same as Hierarchical)."""
    def __init__(self, loader: DataLoader):
        self.loader = loader
        self.dataset = loader.dataset

    def __iter__(self):
        for images, labels in self.loader:
            yield {"img": images, "label": labels}

    def __len__(self):
        return len(self.loader)

class SpykerSimulation:
    def __init__(self):
        self.server_ids = []
        self.client_ids = []

        self.client_registry: Dict[str, ClientSpec] = {}
        self.server_registry: Dict[str, ServerSpec] = {}

        self.client_map: Dict[str, List[Tuple[str, SimulationFlowerClient]]] = {}

        self.config = FullConfiguration()

        self.context = None
        self.orchestrator = None
        self.spyker_actors_map: Dict[str, Any] = {}

    def set_configurations(self, 
                           spyker_params: Dict[str, Any],
                           training_params: Dict[str, Any],
                           simulation_params: Dict[str, Any]):
        """
        API Entry point to inject configurations before build/run.
        Values not provided will fallback to defaults in spyker_config.py
        """
        
        # 1. Update Spyker Algorithm Params
        if spyker_params:
            for k, v in spyker_params.items():
                if hasattr(self.config.spyker, k):
                    setattr(self.config.spyker, k, v)
                else:
                    print(f"[Warning] Unknown Spyker config key: {k}")

        # 2. Update Training Params
        if training_params:
            for k, v in training_params.items():
                if hasattr(self.config.training, k):
                    setattr(self.config.training, k, v)

        # 3. Update Simulation Physics Params
        if simulation_params:
            for k, v in simulation_params.items():
                if hasattr(self.config.simulation, k):
                    setattr(self.config.simulation, k, v)

        print("Configuration Updated.")
        print(f"  > Run Limit: {self.config.simulation.run_time_limit}s")
        print(f"  > Epochs: {self.config.training.local_epochs}")
        print(f"  > Token Heartbeat: {self.config.simulation.idle_token_delay}s")

    def add_server(
            self, 
            server_id: str, 
            name: str, 
            perf: Performance, 
            net: Dict[str, Network], 
            download_speed: float, 
            upload_speed: float
        ):
        """NOTE: net parameter may only take in server_ids in order to establish server to server connections."""
        if server_id not in self.server_ids:
            self.server_ids.append(server_id)
        
        self.server_registry[server_id] = ServerSpec(
            id = server_id,
            name = name,
            performance_metrics = perf,
            network_metrics = net,
            download_speed=download_speed,
            upload_speed=upload_speed
        )
        if server_id not in self.client_map:
            self.client_map[server_id] = []
    
    def add_client(
        self,
        client_id: str,
        server_id: str,
        name: str,
        perf: Performance,
        dataset_partition_id: int,
        total_partitions: int,
        download_speed: float, 
        upload_speed: float
    ):
        """Registers a client configuration and assigns it to a spyker server."""
        if server_id not in self.server_ids:
            raise ValueError(
                f"Spyker server {server_id} must be added before assigning clients."
            )

        self.client_ids.append(client_id)
        self.client_registry[client_id] = ClientSpec(
            id=client_id,
            name=name,
            performance_metrics=perf,
            download_speed=download_speed,
            upload_speed=upload_speed
        )

        sim_client = SimulationFlowerClient(dataset_partition_id, total_partitions)
        self.client_map[server_id].append((client_id, sim_client))

    def _spawn_actors(self):
        if not self.server_ids:
            raise ValueError("No servers defined.")

        first_server = self.server_ids[0]
        if not self.client_map[first_server]:
            raise ValueError(
                "First spyker server must have at least one client to initialize global model."
            )
        
        first_client_sim = self.client_map[first_server][0][1]
        initial_params = first_client_sim.get_parameters(config={})
        initial_weights_np = parameters_to_ndarrays(initial_params)

        print(f"Spawning {len(self.server_ids)} Spyker Servers...")

        for s_id in self.server_ids:
            actor = SpykerServer.remote(
                server_id=s_id,
                config=self.config,
                context=self.context
            )
            self.spyker_actors_map[s_id] = actor

        self.context.set_server_actor_handles(self.spyker_actors_map)

        for s_id in self.server_ids:
            actor = self.spyker_actors_map[s_id]

            # Update Context
            ray.get(actor.set_global_context_remote.remote(self.context))
            
            # Inject Orchestrator & Weights
            ray.get(actor.set_orchestrator.remote(self.orchestrator))
            ray.get(actor.set_initial_weights.remote(initial_weights_np))

            # Register Clients
            assigned_clients = {
                c_id: sim_client
                for c_id, sim_client in self.client_map[s_id]
            }
            ray.get(actor.register_clients.remote(assigned_clients))
    
    def _configure_network(self):
        print("Wiring Spyker Mesh and Token Ring...")

        count = len(self.server_ids)

        for i, s_id in enumerate(self.server_ids):
            actor = self.spyker_actors_map[s_id]

            server_ids_set = set(self.server_ids)

            outbound_edges = {
                k: v
                for k, v in self.server_registry.get(s_id).network_metrics.items()
                if k in server_ids_set
            }

            next_peer_id = self.server_ids[(i + 1) % count] # TODO: implement cohesive selection strategy for ring

            assigned_client_ids = [c_id for c_id, _ in self.client_map[s_id]]

            ray.get(actor.set_topology.remote(
                peer_connections = outbound_edges,
                next_token_peer=next_peer_id,
                assigned_clients = assigned_client_ids
            ))

            if i == 0:
                print(f"Server {s_id} designated as Initial Token Holder.")
                ray.get(actor.set_token_holder.remote(True))
    
    def build(self):
        initialize_environment()

        self.orchestrator = SimulationOrchestrator.remote()

        self.context = SimulationContext(
            orchestrator_actor=self.orchestrator,
            client_registry=self.client_registry,
            server_registry=self.server_registry
        )

        set_global_context(self.context)

        self._spawn_actors()

        self._configure_network()
    
    def run(self):
        if not self.orchestrator:
            raise RuntimeError("Simulation not built. Call build() first.")
        
        print("Initializing Spyker simulation...")

        all_initial_events = []
        for s_id, actor in self.spyker_actors_map.items():
            events = ray.get(actor.start_simulation.remote())
            if events:
                all_initial_events.extend(events)
        
        for delay, target, method, payload in all_initial_events:
            ray.get(self.orchestrator.add_event.remote(delay, target, method, payload))

        print(f"Simulation queued with {len(all_initial_events)} initial events.")
        print("Running orchestration loop...")
        limit = self.config.simulation.run_time_limit

        ray.get(self.orchestrator.run_until.remote(limit))

        print("Simulation execution finished")

    def save_model(self, filename: str):
        target_server = self.server_ids[0]
        actor = self.spyker_actors_map[target_server]

        print(f"Extracting final model from Server {target_server}...")
        final_weights_np = ray.get(actor.get_global_model.remote())

        dummy_model = Net()
        keys = dummy_model.state_dict().keys()

        state_dict = OrderedDict(
            {k: torch.tensor(v) for k, v in zip(keys, final_weights_np)}
        )

        torch.save(state_dict, filename)
        print(f"Model successfully saved to {filename}")
    
    # ===========================

def initialize_environment():
    if ray.is_initialized():
        ray.shutdown()
    ray.init()
    print("Ray environment initialized.")
    
def evaluate_model(filename: str):
    print(f"Starting evaluation for model: {filename}")
    device = torch.device("cpu")
    model = Net()
    model.to(device)
    state_dict = torch.load(filename)
    model.load_state_dict(state_dict, strict=True)

    transform = Compose([ToTensor(), Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    test_set = CIFAR10(root="./data", train=False, download=True, transform=transform)
    test_loader = DataLoader(test_set, batch_size=32, shuffle=False)

    adapter = DataLoaderAdapter(test_loader)
    avg_loss, accuracy = test(model, adapter, device)

    print("=" * 30)
    print(f"SPYKER FINAL RESULTS")
    print(f"Accuracy: {accuracy*100:.2f}%")
    print(f"Avg Loss: {avg_loss:.4f}")
    print("=" * 30)

    # ==============================================================

def run_default_simulation():
    print("Initialising Simulation.")
    sim = SpykerSimulation()

    # --- INJECT CONFIGURATIONS ---
    sim.set_configurations(
        spyker_params={
            "decay_beta": 0.1,
            "min_learning_rate": 1e-6,
            "h_inter": 5,
            "h_intra": 350,
            "sigmoid_phi": 1.5,
            "server_learning_rate": 0.6,
            "tcp_rto_delay": 0.2
        },
        training_params={
            "local_epochs": 1,
            "learning_rate": 0.05,
            "model_complexity": 1.0
        },
        simulation_params={
            "run_time_limit": 2000.0,
            "idle_token_delay": 1.0
        }
    )

    perf = Performance(compute_factor=10.0, performance_stddev=1.0)

    net_client = Network(latency_avg=20, latency_stddev=5, packet_loss_avg=0.001, packet_loss_stddev=0)

    net_backbone = Network(latency_avg=50, latency_stddev=2, packet_loss_avg=0.01, packet_loss_stddev=0)

    download_speed_client = 100
    download_speed_server = 1000
    upload_speed_client = 20
    upload_speed_server = 1000

    s1, s2, s3 = "server_A", "server_B", "server_C"
    s1_edges: Dict[str, Network] = {}
    s1_edges['server_B'] = net_backbone
    s1_edges['server_C'] = net_backbone
    s2_edges: Dict[str, Network] = {}
    s2_edges['server_A'] = net_backbone
    s2_edges['server_C'] = net_backbone
    s3_edges: Dict[str, Network] = {}
    s3_edges['server_A'] = net_backbone
    s3_edges['server_B'] = net_backbone
    sim.add_server(s1, "Spyker Node A", perf, s1_edges, download_speed_server, upload_speed_server)
    sim.add_server(s2, "Spyker Node B", perf, s2_edges, download_speed_server, upload_speed_server)
    sim.add_server(s3, "Spyker Node C", perf, s3_edges, download_speed_server, upload_speed_server)

    total_clients = 6
    for i in range(total_clients):
        cid = f"client_{i}"

        if i < 2:
            assigned_server = s1
            s1_edges[cid] = net_client
        elif i < 4:
            assigned_server = s2
            s2_edges[cid] = net_client
        else:
            assigned_server = s3
            s3_edges[cid] = net_client 

        sim.add_client(
            client_id=cid,
            server_id=assigned_server,
            name=cid,
            perf=perf,
            dataset_partition_id=i,
            total_partitions=total_clients,
            download_speed=download_speed_client,
            upload_speed=upload_speed_client
        )
        
    sim.build()
    sim.run()

    out_file = "final_model_spyker.pth"
    sim.save_model(out_file)
    evaluate_model(out_file)

def main():
    run_default_simulation()

if __name__ == "__main__":
    main()
