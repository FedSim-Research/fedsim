import numpy as np
import ray
import torch

from fedsim.clients.training import TrainingClient
from fedsim.simulation.compute_model import estimate_training_time
from fedsim.simulation.context import SimulationContext, get_global_context, set_global_context
from fedsim.simulation.network_model import estimate_transmission_time
from fedsim.simulation.randomness import RandomStreams


@ray.remote(num_cpus=0, num_gpus=0)
class VirtualClientActor:
    def __init__(self, client_id: str, client_config: dict, context: SimulationContext):
        self.client_id = client_id
        self.random_streams = RandomStreams(client_config.get("seed"), "client")
        set_global_context(context)
        torch.set_num_threads(1)

        # Instantiate inner client locally to this actor's process
        # (Prevents serializing un-pickleable PyTorch DataLoaders)
        self.inner_client = TrainingClient(
            partition_id=client_config["dataset_partition_id"],
            num_partitions=client_config["total_partitions"],
            dataset_id=client_config.get("dataset_id"),
            seed=client_config.get("seed"),
            partition_seed=context.seed,
            dataset_provider=context.dataset_provider,
        )
        self.current_virtual_time = 0.0
        self.orchestrator_ref = None

    def set_orchestrator(self, orchestrator_ref):
        self.orchestrator_ref = orchestrator_ref

    def handle_event(self, payload: dict, direct_refs=None):
        event_type = payload.get("event_type")
        trigger_time = payload.get("trigger_time")
        data = payload.get("data")

        self.current_virtual_time = trigger_time

        if event_type == "START_FIT":
            return self.fit(data, direct_refs)
        elif event_type == "START_EVALUATE":
            return self.evaluate(data, direct_refs)
        else:
            print(f"[VirtualClient {self.client_id}] Unknown event: {event_type}")
            return []

    def fit(self, data: dict, direct_refs: list[np.ndarray]):
        server_id = data["server_id"]
        server_ref = data["server_ref"]
        config = data["config"]

        ctx = get_global_context()
        client_spec = ctx.get_client_spec(self.client_id)
        server_spec = ctx.get_server_spec(server_id)

        epochs = int(config.get("epochs", 1))
        model_complexity = float(config.get("model_complexity", 1.0))
        ref_model_age = config.get("model_age", 0)

        param_arrays = direct_refs
        model_size_bytes = sum(a.nbytes for a in param_arrays)

        t_download = estimate_transmission_time(
            sender_spec=server_spec,
            receiver_spec=client_spec,
            network_metrics=server_spec.network_metrics,
            metrics_id=self.client_id,
            payload_size_bytes=model_size_bytes,
            rng=self.random_streams.stream("download", server_id),
        )

        fit_res = self.inner_client.fit(parameters=param_arrays, config=config)

        t_train = estimate_training_time(
            client_spec=client_spec,
            dataset_size=fit_res["num_examples"],
            epochs=epochs,
            model_complexity=model_complexity,
            rng=self.random_streams.stream("training"),
        )

        res_arrays = fit_res["parameters"]
        res_size_bytes = sum(a.nbytes for a in res_arrays)

        t_upload = estimate_transmission_time(
            sender_spec=client_spec,
            receiver_spec=server_spec,
            network_metrics=server_spec.network_metrics,
            metrics_id=self.client_id,
            payload_size_bytes=res_size_bytes,
            rng=self.random_streams.stream("upload", server_id),
        )

        total_virtual_duration = t_download + t_train + t_upload

        metrics = fit_res.get("metrics", {})
        metrics["simulation_duration"] = total_virtual_duration
        metrics["client_id"] = self.client_id
        metrics["ref_model_age"] = ref_model_age

        weights_ref = ray.put(res_arrays)

        return [
            (
                total_virtual_duration,
                server_ref,
                "handle_event",
                {
                    "event_type": "CLIENT_UPDATE",
                    "trigger_time": self.current_virtual_time + total_virtual_duration,
                    "data": {
                        "client_id": self.client_id,
                        "server_id": server_id,
                        "num_examples": fit_res["num_examples"],
                        "metrics": metrics,
                    },
                },
                weights_ref,
            )
        ]
