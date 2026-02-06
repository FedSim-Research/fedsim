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
from specs.server_spec import ServerSpec
from specs.client_spec import ClientSpec
from specs.network_metrics import Network
from specs.performance_metrics import Performance
from server.hierarchical.super_server_actor import SuperServer
from server.hierarchical.edge_server_actor import EdgeServer
from client.simulation_client import SimulationFlowerClient

RUNTIME_LIMIT = 5000.0
SUPER_ID = "super_server"
EDGE_IDS = ["edge_1", "edge_2"]
TOTAL_CLIENTS = 4


class DataLoaderAdapter:
    """
    Wraps a standard Torchvision DataLoader to be compatible with evaluation functions
    that expect a dictionary-style yield (e.g., HuggingFace/Flower FederatedDataset).
    """

    def __init__(self, loader: DataLoader):
        self.loader = loader
        self.dataset = loader.dataset

    def __iter__(self):
        for images, labels in self.loader:
            yield {"img": images, "label": labels}

    def __len__(self):
        return len(self.loader)


class HierarchicalSimulation:
    """See Hierarchical_Simulation_README.md for details on the simulation setup and how to use it."""

    def __init__(self, run_time_limit: float = RUNTIME_LIMIT):
        self.run_time_limit = run_time_limit
        self.super_id = None
        self.edge_ids = []
        self.client_ids = []
        self.client_map: Dict[str, List[Tuple[str, SimulationFlowerClient]]] = {}

        self.client_registry: Dict[str, ClientSpec] = {}
        self.server_registry: Dict[str, ServerSpec] = {}

        self.super_config = None
        self.edge_configs = {}

        self.context = None
        self.orchestrator = None
        self.super_actor = None
        self.edge_actors_map = {}

    def set_super_server(
        self,
        server_id: str,
        name: str,
        perf: Performance,
        upload_speed: float,
        download_speed: float,
        training_config: Dict[str, Any],
    ):
        """Registers the super server configuration."""
        self.super_id = server_id
        self.server_registry[server_id] = ServerSpec(
            id=server_id,
            name=name,
            performance_metrics=perf,
            network_metrics=None,
            upload_speed=upload_speed,
            download_speed=download_speed,
        )
        self.super_config = training_config

    def add_edge_server(
        self,
        server_id: str,
        name: str,
        perf: Performance,
        net: dict[str, Network],
        upload_speed: float,
        download_speed: float,
    ):
        """Registers an edge server configuration."""
        if server_id not in self.edge_ids:
            self.edge_ids.append(server_id)

        self.server_registry[server_id] = ServerSpec(
            id=server_id,
            name=name,
            performance_metrics=perf,
            network_metrics=net,
            upload_speed=upload_speed,
            download_speed=download_speed,
        )
        if server_id not in self.client_map:
            self.client_map[server_id] = []

    def add_client(
        self,
        client_id: str,
        edge_id: str,
        name: str,
        perf: Performance,
        upload_speed: float,
        download_speed: float,
        dataset_partition_id: int,
        total_partitions: int,
    ):
        """Registers a client configuration and assigns it to an edge server."""
        if edge_id not in self.edge_ids:
            raise ValueError(
                f"Edge server {edge_id} must be added before assigning clients."
            )

        self.client_ids.append(client_id)
        self.client_registry[client_id] = ClientSpec(
            id=client_id,
            name=name,
            performance_metrics=perf,
            upload_speed=upload_speed,
            download_speed=download_speed,
        )

        sim_client = SimulationFlowerClient(dataset_partition_id, total_partitions)
        self.client_map[edge_id].append((client_id, sim_client))

    def _spawn_actors(self):
        """Spawns the SuperServer and EdgeServer actors on the Ray cluster."""
        first_edge = self.edge_ids[0]
        if not self.client_map[first_edge]:
            raise ValueError(
                "First edge server must have at least one client to initialize global model."
            )

        first_client = self.client_map[first_edge][0][1]
        initial_params = first_client.get_parameters(config={})
        initial_weights = parameters_to_ndarrays(initial_params)

        print(f"Spawning Super Server ({self.super_id})...")
        self.super_actor = SuperServer.remote(
            server_id=self.super_id,
            initial_parameters=initial_weights,
            required_updates=len(self.edge_ids),
            training_config=self.super_config,
            context=self.context,
        )

        print("Spawning Edge Servers...")
        for eid in self.edge_ids:
            assigned_clients = self.client_map[eid]
            edge_actor = EdgeServer.remote(
                server_id=eid,
                super_server_id=self.super_id,
                super_server_ref=self.super_actor,
                assigned_clients=assigned_clients,
                min_clients_per_round=len(assigned_clients),
                context=self.context,
            )
            self.edge_actors_map[eid] = edge_actor

    def _configure_network(self):
        """Wiring server connections."""
        print("Wiring server connections...")
        ray.get(self.super_actor.set_edge_servers.remote(self.edge_actors_map))

        all_servers = [self.super_actor] + list(self.edge_actors_map.values())
        for srv in all_servers:
            ray.get(srv.set_orchestrator.remote(self.orchestrator))

    def build(self):
        """Constructs the simulation environment, orchestrator, and actors."""
        initialize_environment()

        self.orchestrator = SimulationOrchestrator.remote()
        self.context = SimulationContext(
            orchestrator_actor=self.orchestrator,
            client_registry=self.client_registry,
            server_registry=self.server_registry,
        )
        set_global_context(self.context)

        if not self.super_id:
            raise ValueError("Super server must be defined before building.")
        if not self.edge_ids:
            raise ValueError("At least one edge server must be defined.")

        self._spawn_actors()
        self._configure_network()

    def run(self):
        """Runs the simulation loop."""
        if not self.orchestrator or not self.super_actor:
            raise RuntimeError("Simulation not built. Call build() first.")

        print("Initializing simulation...")
        initial_events = ray.get(self.super_actor.start_simulation.remote())

        for delay, target, method, payload in initial_events:
            ray.get(self.orchestrator.add_event.remote(delay, target, method, payload))

        print(f"Simulation started with {len(initial_events)} initial events.")
        print("Running simulation loop...")
        ray.get(self.orchestrator.run_until.remote(self.run_time_limit))
        print("Simulation execution finished.")

    def save_model(self, filename: str):
        """Fetches the final model weights and saves them."""
        print("Extracting final model...")
        final_weights_np = ray.get(self.super_actor.get_global_model.remote())

        dummy_model = Net()
        keys = dummy_model.state_dict().keys()

        state_dict = OrderedDict(
            {k: torch.tensor(v) for k, v in zip(keys, final_weights_np)}
        )

        torch.save(state_dict, filename)
        print(f"Model successfully saved to {filename}")


def initialize_environment():
    """Initializes the Ray runtime."""
    if ray.is_initialized():
        ray.shutdown()
    try:
        ray.init(address="auto")
        print("Ray environment initialized (connected to existing cluster).")
    except Exception:
        ray.init()
        print("Ray environment initialized (local).")


def evaluate_model(filename: str):
    """
    Loads a saved model checkpoint and evaluates it against the CIFAR-10 test set.
    """
    print(f"Starting evaluation for model: {filename}")
    device = torch.device("cpu")

    model = Net()
    model.to(device)

    state_dict = torch.load(filename)
    model.load_state_dict(state_dict, strict=True)

    transform = Compose([ToTensor(), Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])
    test_set = CIFAR10(root="./data", train=False, download=True, transform=transform)
    test_loader = DataLoader(test_set, batch_size=32, shuffle=False)

    print(f"Evaluating on {len(test_set)} samples...")
    adapter = DataLoaderAdapter(test_loader)
    avg_loss, accuracy = test(model, adapter, device)

    print("=" * 30)
    print(f"FINAL RESULTS")
    print(f"Accuracy: {accuracy*100:.2f}%")
    print(f"Avg Loss: {avg_loss:.4f}")
    print("=" * 30)
    return {"accuracy": float(accuracy), "avg_loss": float(avg_loss)}


def run_default_simulation():
    """
    Sets up and runs the default simulation configuration using the API.
    """
    sim = HierarchicalSimulation(run_time_limit=RUNTIME_LIMIT)

    default_perf = Performance(10, 1)
    default_net = Network(15, 5, 0.001, 0.0005)
    default_upload = 20
    default_download = 100
    default_net_dict = {}
    default_net_dict[SUPER_ID] = (default_net)
    for i in range(TOTAL_CLIENTS):
        default_net_dict[f"client_{i}"] = (default_net)

    sim.set_super_server(
        server_id=SUPER_ID,
        name="Super Server",
        perf=default_perf,
        upload_speed=default_upload,
        download_speed=default_download,
        training_config={"epochs": 1, "lr": 0.01},
    )

    for eid in EDGE_IDS:
        sim.add_edge_server(
            eid, eid, default_perf, default_net_dict, default_upload, default_download
        )

    clients_per_edge = TOTAL_CLIENTS // len(EDGE_IDS)

    client_idx = 0
    for eid in EDGE_IDS:
        for _ in range(clients_per_edge):
            cid = f"client_{client_idx}"
            sim.add_client(
                client_id=cid,
                edge_id=eid,
                name=cid,
                perf=default_perf,
                upload_speed=default_upload,
                download_speed=default_download,
                dataset_partition_id=client_idx,
                total_partitions=TOTAL_CLIENTS,
            )
            client_idx += 1

    sim.build()
    sim.run()

    output_filename = "final_model_hierarchical.pth"
    sim.save_model(output_filename)
    evaluate_model(output_filename)


def main():
    run_default_simulation()


if __name__ == "__main__":
    main()
