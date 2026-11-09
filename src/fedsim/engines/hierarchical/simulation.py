from collections import OrderedDict
from typing import Any, Dict, List, Tuple

import ray
import torch

from fedsim.engines.hierarchical.coordinator import SuperServer
from fedsim.engines.hierarchical.edge import EdgeServer
from fedsim.learning import Net, get_dataset_provider
from fedsim.runtime import ensure_ray_initialized
from fedsim.simulation.context import SimulationContext, set_global_context
from fedsim.simulation.cpu_execution import get_cpu_execution_pool
from fedsim.simulation.orchestrator import SimulationOrchestrator
from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec

RUNTIME_LIMIT = 5000.0


class HierarchicalSimulation:
    """Hierarchical aggregation over client groups, edge servers, and a coordinator."""

    def __init__(
        self,
        dataset_id: str = "uoft-cs/cifar10",
        run_time_limit: float = RUNTIME_LIMIT,
        gpu_budget: float | None = None,
        seed: int | None = None,
    ):
        self.dataset_id = dataset_id
        self.run_time_limit = run_time_limit
        self.gpu_budget = gpu_budget
        self.seed = seed
        self.super_id = None
        self.edge_ids = []
        self.client_ids = []
        self.client_map: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}

        self.client_registry: Dict[str, ClientSpec] = {}
        self.server_registry: Dict[str, ServerSpec] = {}

        self.super_config = None
        self.edge_configs = {}

        self.context = None
        self.orchestrator = None
        self._cpu_pool = None
        self.super_actor = None
        self.edge_actors_map = {}
        self._server_actor_options: dict[str, float] = {}
        self.evaluator_actor = None
        self.eval_interval = 0.0
        self.run_id = "unknown_run"
        self.graph_id = -1

    def set_metadata(self, run_id: str, graph_id: str, eval_interval: float | None = None):
        """Configure telemetry settings."""
        if run_id:
            self.run_id = run_id
        if graph_id is not None:
            self.graph_id = int(graph_id)
        if eval_interval is not None:
            self.eval_interval = max(0.0, float(eval_interval))
        else:
            self.eval_interval = 500

    def _resolve_server_actor_options(self) -> dict[str, float]:
        if self.gpu_budget is None:
            return {}
        available_gpu = float(ray.available_resources().get("GPU", 0.0))
        requested_gpu = max(0.0, float(self.gpu_budget))
        if available_gpu <= 1e-3 and requested_gpu > 0.0:
            print(
                "HierFL GPU budget requested but effective cluster GPU capacity is near zero; "
                "falling back to CPU actor placement."
            )
            requested_gpu = 0.0
        elif requested_gpu > available_gpu + 1e-9:
            print(
                f"HierFL GPU budget exceeds available resources; capping budget "
                f"from {requested_gpu} to {available_gpu}."
            )
            requested_gpu = available_gpu
        actor_count = len(self.edge_ids) + 1  # super server + edge servers
        if actor_count < 1:
            return {}
        gpu_per_actor = max(0.0, requested_gpu / float(actor_count))
        print(
            f"Applying dynamic GPU allocation (HierFL): budget={self.gpu_budget}, "
            f"actors={actor_count}, num_gpus_per_actor={gpu_per_actor}"
        )
        return {"num_gpus": gpu_per_actor}

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
        seed: int | None = None,
    ):
        """Registers a client configuration and assigns it to an edge server."""
        if edge_id not in self.edge_ids:
            raise ValueError(f"Edge server {edge_id} must be added before assigning clients.")

        self.client_ids.append(client_id)
        self.client_registry[client_id] = ClientSpec(
            id=client_id,
            name=name,
            performance_metrics=perf,
            upload_speed=upload_speed,
            download_speed=download_speed,
        )

        client_config = {
            "dataset_id": self.dataset_id,
            "dataset_partition_id": dataset_partition_id,
            "total_partitions": total_partitions,
            "seed": seed,
        }
        self.client_map[edge_id].append((client_id, client_config))

    def _spawn_actors(self):
        """Spawns the SuperServer and EdgeServer actors on the Ray cluster."""
        first_edge = self.edge_ids[0]
        if not self.client_map[first_edge]:
            raise ValueError(
                "First edge server must have at least one client to initialize global model."
            )

        dummy_model = Net(seed=self.seed)
        initial_weights = [val.cpu().numpy() for _, val in dummy_model.state_dict().items()]

        print(f"Spawning Super Server ({self.super_id})...")
        self.super_actor = SuperServer.options(**self._server_actor_options).remote(
            server_id=self.super_id,
            initial_parameters=initial_weights,
            required_updates=len(self.edge_ids),
            training_config=self.super_config,
            context=self.context,
        )

        print("Spawning Edge Servers...")
        for eid in self.edge_ids:
            edge_actor = EdgeServer.options(**self._server_actor_options).remote(
                server_id=eid,
                super_server_id=self.super_id,
                super_server_ref=self.super_actor,
                min_clients_per_round=len(self.client_map[eid]),
                context=self.context,
            )
            self.edge_actors_map[eid] = edge_actor

        # Update context locally
        all_actors = {self.super_id: self.super_actor}
        all_actors.update(self.edge_actors_map)
        self.context.set_server_actor_handles(all_actors)

        # Distribute context and register clients safely on the edge workers
        for eid in self.edge_ids:
            actor = self.edge_actors_map[eid]
            ray.get(actor.set_global_context_remote.remote(self.context))

            assigned_client_configs = {c_id: config for c_id, config in self.client_map[eid]}
            ray.get(actor.register_clients.remote(assigned_client_configs))

    def _configure_network(self):
        """Wiring server connections."""
        print("Wiring server connections...")
        ray.get(self.super_actor.set_edge_servers.remote(self.edge_actors_map))

        all_servers = [self.super_actor] + list(self.edge_actors_map.values())
        for srv in all_servers:
            ray.get(srv.set_orchestrator.remote(self.orchestrator))

    def build(self):
        """Constructs the simulation environment, orchestrator, and actors."""
        if not self.super_id:
            raise ValueError("Super server must be defined before building.")
        if not self.edge_ids:
            raise ValueError("At least one edge server must be defined.")
        ensure_ray_initialized()

        self._cpu_pool = get_cpu_execution_pool()
        self._server_actor_options = self._resolve_server_actor_options()
        self.orchestrator = SimulationOrchestrator.remote(cpu_pool=self._cpu_pool)
        self.context = SimulationContext(
            orchestrator_actor=self.orchestrator,
            client_registry=self.client_registry,
            server_registry=self.server_registry,
            seed=self.seed,
            dataset_provider=get_dataset_provider(
                self.dataset_id, len(self.client_registry), self.seed
            ),
        )
        set_global_context(self.context)

        self._spawn_actors()
        self._configure_network()

    def run(self):
        """Runs the simulation loop."""
        if not self.orchestrator or not self.super_actor:
            raise RuntimeError("Simulation not built. Call build() first.")

        print("Initializing simulation...")
        all_initial_events = []

        # --- EVALUATOR INITIALIZATION ---
        if getattr(self, "eval_interval", 0.0) > 0:
            from fedsim.telemetry.evaluator import PeriodicEvaluator

            print(f"Spawning Periodic Evaluator (Interval: {self.eval_interval}s)...")
            self.evaluator_actor = PeriodicEvaluator.remote(
                run_id=str(self.run_id),
                graph_id=self.graph_id,
                architecture="hierarchical",
                target_server_ref=self.super_actor,
                orchestrator_ref=self.orchestrator,
                evaluation_interval=self.eval_interval,
                dataset=self.dataset_id,
            )

            # Fetch the first event (T=0 evaluation + scheduling the next)
            eval_events = ray.get(self._cpu_pool.call.remote(self.evaluator_actor, "start", (), {}))
            if eval_events:
                all_initial_events.extend(eval_events)
        # ---------------------------------

        server_events = ray.get(self.super_actor.start_simulation.remote())
        if server_events:
            all_initial_events.extend(server_events)

        for event in all_initial_events:
            if len(event) == 5:
                delay, target, method, payload, refs = event
                ray.get(self.orchestrator.add_event.remote(delay, target, method, payload, refs))
            elif len(event) == 4:
                delay, target, method, payload = event
                ray.get(self.orchestrator.add_event.remote(delay, target, method, payload))
            else:
                raise ValueError(f"Unexpected event tuple length: {len(event)}")

        print(f"Simulation started with {len(all_initial_events)} initial events.")
        print("Running simulation loop...")

        ray.get(self.orchestrator.run_until.remote(self.run_time_limit))

        print("Simulation execution finished.")

    def save_model(self, filename: str):
        """Fetches the final model weights and saves them."""
        print("Extracting final model...")
        final_weights_np = ray.get(self.super_actor.get_global_model.remote())

        dummy_model = Net()
        keys = dummy_model.state_dict().keys()

        state_dict = OrderedDict({k: torch.tensor(v) for k, v in zip(keys, final_weights_np)})

        torch.save(state_dict, filename)
        print(f"Model successfully saved to {filename}")
