from collections import OrderedDict
from pathlib import Path
from typing import Any, Dict, List, Tuple

import ray
import torch

from fedsim.engines.spyker.server import SpykerServer
from fedsim.learning import DEFAULT_LOCAL_HOLDOUT, Net, get_dataset_provider
from fedsim.runtime import ensure_ray_initialized
from fedsim.simulation.context import SimulationContext, set_global_context
from fedsim.simulation.cpu_execution import get_cpu_execution_pool
from fedsim.simulation.orchestrator import SimulationOrchestrator
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


class SpykerSimulation:
    def __init__(
        self,
        dataset_id: str = "uoft-cs/cifar10",
        gpu_budget: float | None = None,
        seed: int | None = None,
        partitioning: str = "iid",
        labels_per_client: int | None = None,
        local_holdout: float = DEFAULT_LOCAL_HOLDOUT,
    ):
        self.dataset_id = dataset_id
        self.gpu_budget = gpu_budget
        self.seed = seed
        self.partitioning = partitioning
        self.labels_per_client = labels_per_client
        self.local_holdout = local_holdout
        self.server_ids = []
        self.client_ids = []

        self.client_registry: Dict[str, ClientSpec] = {}
        self.server_registry: Dict[str, ServerSpec] = {}

        self.client_map: Dict[str, List[Tuple[str, Any]]] = {}

        self.config = FullConfiguration()

        self.context = None
        self.orchestrator = None
        self._cpu_pool = None
        self.spyker_actors_map: Dict[str, Any] = {}
        self._server_actor_options: dict[str, float] = {}
        self.run_id = "unknown_run"
        self.graph_id = -1
        self.eval_interval = 0.0
        self.evaluator_actor = None

    def _resolve_server_actor_options(self) -> dict[str, float]:
        if self.gpu_budget is None:
            return {}
        available_gpu = float(ray.available_resources().get("GPU", 0.0))
        requested_gpu = max(0.0, float(self.gpu_budget))
        if available_gpu <= 1e-3 and requested_gpu > 0.0:
            print(
                "Spyker GPU budget requested but effective cluster GPU capacity is near zero; "
                "falling back to CPU actor placement."
            )
            requested_gpu = 0.0
        elif requested_gpu > available_gpu + 1e-9:
            print(
                f"Spyker GPU budget exceeds available resources; capping budget "
                f"from {requested_gpu} to {available_gpu}."
            )
            requested_gpu = available_gpu
        actor_count = len(self.server_ids)
        if actor_count < 1:
            return {}
        gpu_per_actor = max(0.0, requested_gpu / float(actor_count))
        print(
            f"Applying dynamic GPU allocation (Spyker): budget={self.gpu_budget}, "
            f"actors={actor_count}, num_gpus_per_actor={gpu_per_actor}"
        )
        return {"num_gpus": gpu_per_actor}

    def set_configurations(
        self,
        spyker_params: Dict[str, Any],
        training_params: Dict[str, Any],
        simulation_params: Dict[str, Any],
    ):
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

    def set_metadata(self, run_id: str, graph_id: str, eval_interval: float | None = None):
        """Configure telemetry settings."""
        if run_id:
            self.run_id = run_id
        if graph_id:
            self.graph_id = graph_id
        if eval_interval is None:
            self.eval_interval = self.config.simulation.eval_time_delay
        else:
            self.eval_interval = max(0.0, float(eval_interval))

    def add_server(
        self,
        server_id: str,
        name: str,
        perf: Performance,
        net: Dict[str, Network],
        download_speed: float,
        upload_speed: float,
    ):
        """NOTE: net parameter may only take in server_ids in order to establish server to server connections."""
        if server_id not in self.server_ids:
            self.server_ids.append(server_id)

        self.server_registry[server_id] = ServerSpec(
            id=server_id,
            name=name,
            performance_metrics=perf,
            network_metrics=net,
            download_speed=download_speed,
            upload_speed=upload_speed,
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
        upload_speed: float,
        seed: int | None = None,
    ):
        """Registers a client configuration and assigns it to a spyker server."""
        if server_id not in self.server_ids:
            raise ValueError(f"Spyker server {server_id} must be added before assigning clients.")

        self.client_ids.append(client_id)
        self.client_registry[client_id] = ClientSpec(
            id=client_id,
            name=name,
            performance_metrics=perf,
            download_speed=download_speed,
            upload_speed=upload_speed,
        )

        client_config = {
            "dataset_id": self.dataset_id,
            "dataset_partition_id": dataset_partition_id,
            "total_partitions": total_partitions,
            "seed": seed,
        }
        self.client_map[server_id].append((client_id, client_config))

    def _resolve_h_inter(self):
        if self.config.spyker.h_inter == "auto":
            # n_C / (5n), rounded to the nearest integer (ties to even), at least 1.
            self.config.spyker.h_inter = max(
                1, round(len(self.client_ids) / (5 * len(self.server_ids)))
            )

    def _spawn_actors(self):
        if not self.server_ids:
            raise ValueError("No servers defined.")

        first_server = self.server_ids[0]
        if not self.client_map[first_server]:
            raise ValueError(
                "First spyker server must have at least one client to initialize global model."
            )

        self._resolve_h_inter()

        dummy_model = Net(seed=self.seed)
        initial_weights_np = [val.cpu().numpy() for _, val in dummy_model.state_dict().items()]

        print(f"Spawning {len(self.server_ids)} Spyker Servers...")

        for s_id in self.server_ids:
            actor = SpykerServer.options(**self._server_actor_options).remote(
                server_id=s_id, config=self.config, context=self.context
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
            assigned_client_configs = {
                c_id: client_config for c_id, client_config in self.client_map[s_id]
            }
            ray.get(actor.register_clients.remote(assigned_client_configs))

    def _configure_network(self):
        print("Wiring Spyker Mesh and Token Ring...")

        count = len(self.server_ids)

        for i, s_id in enumerate(self.server_ids):
            actor = self.spyker_actors_map[s_id]

            server_ids_set = set(self.server_ids)

            outbound_edges = {
                k: v
                for k, v in self.server_registry.get(s_id).network_metrics.items()
                if k in server_ids_set and k != s_id
            }

            next_peer_id = self.server_ids[(i + 1) % count] if count > 1 else None

            assigned_client_ids = [c_id for c_id, _ in self.client_map[s_id]]

            ray.get(
                actor.set_topology.remote(
                    peer_connections=outbound_edges,
                    next_token_peer=next_peer_id,
                    assigned_clients=assigned_client_ids,
                )
            )

            if i == 0:
                print(f"Server {s_id} designated as Initial Token Holder.")
                ray.get(actor.set_token_holder.remote(True))

    def build(self):
        server_ids = set(self.server_ids)
        for server_id in server_ids:
            peers = set(self.server_registry[server_id].network_metrics)
            if not server_ids.difference({server_id}).issubset(peers):
                raise ValueError("spyker_requires_fully_connected_servers")
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
                self.dataset_id,
                len(self.client_registry),
                self.seed,
                self.partitioning,
                self.labels_per_client,
                self.local_holdout,
            ),
        )

        set_global_context(self.context)

        self._spawn_actors()

        self._configure_network()

    def close(self):
        """Release this run's logical client state from the shared CPU workers."""
        if self._cpu_pool is not None and self.context is not None:
            ray.get(self._cpu_pool.release_clients.remote(self.context.execution_id))

    def run(self):
        if not self.orchestrator:
            raise RuntimeError("Simulation not built. Call build() first.")

        print("Initializing Spyker simulation...")
        all_initial_events = []

        # Telemetry
        if self.eval_interval > 0:
            from fedsim.telemetry.evaluator import PeriodicEvaluator

            target_srv = self.spyker_actors_map[self.server_ids[0]]

            self.evaluator_actor = PeriodicEvaluator.remote(
                run_id=self.run_id,
                graph_id=self.graph_id,
                architecture="spyker",
                target_server_ref=target_srv,
                orchestrator_ref=self.orchestrator,
                evaluation_interval=self.eval_interval,
                dataset=self.dataset_id,
                target_servers=self.spyker_actors_map,
            )

            eval_events = ray.get(self._cpu_pool.call.remote(self.evaluator_actor, "start", (), {}))
            if eval_events:
                all_initial_events.extend(eval_events)

        for s_id, actor in self.spyker_actors_map.items():
            events = ray.get(actor.start_simulation.remote())
            if events:
                all_initial_events.extend(events)

        for event in all_initial_events:
            if len(event) == 5:
                delay, target, method, payload, refs = event
                ray.get(self.orchestrator.add_event.remote(delay, target, method, payload, refs))
            elif len(event) == 4:
                delay, target, method, payload = event
                ray.get(self.orchestrator.add_event.remote(delay, target, method, payload))
            else:
                raise ValueError(f"Unexpected event tuple length: {len(event)}")

        print(f"Simulation queued with {len(all_initial_events)} initial events.")
        print("Running orchestration loop...")
        limit = self.config.simulation.run_time_limit

        ray.get(self.orchestrator.run_until.remote(limit))
        print("Simulation execution finished")

    def save_model(self, filename: str):
        """Save every server; the requested filename retains the first server."""
        if not self.server_ids:
            raise ValueError("spyker_requires_servers_to_save")
        path = Path(filename)
        keys = Net().state_dict().keys()
        weights = ray.get(
            [
                self.spyker_actors_map[server_id].get_global_model.remote()
                for server_id in self.server_ids
            ]
        )
        checkpoints = {}
        for index, (server_id, arrays) in enumerate(zip(self.server_ids, weights, strict=True)):
            target = (
                path
                if index == 0
                else path.with_name(f"{path.stem}.server-{index + 1}{path.suffix}")
            )
            state = OrderedDict(
                {key: torch.tensor(value) for key, value in zip(keys, arrays, strict=True)}
            )
            torch.save(state, target)
            checkpoints[server_id] = str(target)
        return checkpoints
