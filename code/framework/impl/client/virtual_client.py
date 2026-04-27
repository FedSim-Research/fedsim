import ray
from flwr.common import (
    FitIns,
    FitRes,
    EvaluateIns,
    EvaluateRes,
    parameters_to_ndarrays,
)
from client.simulation_client import SimulationFlowerClient
from simulation.context import get_global_context, SimulationContext, set_global_context
from simulation.compute_model import estimate_training_time
from simulation.network_model import estimate_transmission_time


@ray.remote
class VirtualClientActor:
    def __init__(self, client_id: str, client_config: dict, context: SimulationContext):
        self.client_id = client_id
        set_global_context(context)

        # Instantiate inner client locally to this actor's process
        # (Prevents serializing un-pickleable PyTorch DataLoaders)
        self.inner_client = SimulationFlowerClient(
            partition_id=client_config["dataset_partition_id"],
            num_partitions=client_config["total_partitions"],
            seed=client_config.get("seed"),
        )
        self.current_virtual_time = 0.0
        self.orchestrator_ref = None

    def set_orchestrator(self, orchestrator_ref):
        self.orchestrator_ref = orchestrator_ref

    def handle_event(self, payload: dict, direct_refs=None):
        """Native DES event handler for the Client."""
        event_type = payload.get("event_type")
        trigger_time = payload.get("trigger_time")
        data = payload.get("data")

        self.current_virtual_time = trigger_time

        if event_type == "START_FIT":
            return self.fit(data)
        elif event_type == "START_EVALUATE":
            return self.evaluate(data)
        else:
            print(f"[VirtualClient {self.client_id}] Unknown event: {event_type}")
            return []

    def fit(self, data: dict):
        ins = data["fit_ins"]
        server_id = data["server_id"]
        server_ref = data["server_ref"]

        ctx = get_global_context()
        client_spec = ctx.get_client_spec(self.client_id)
        server_spec = ctx.get_server_spec(server_id)

        config = ins.config
        epochs = int(config.get("epochs", 1))
        model_complexity = float(config.get("model_complexity", 1.0))
        ref_model_age = config.get("model_age", 0)

        param_arrays = parameters_to_ndarrays(ins.parameters)
        model_size_mb = sum([a.nbytes for a in param_arrays]) / (1024 * 1024)

        t_download = estimate_transmission_time(
            sender_spec=server_spec,
            receiver_spec=client_spec,
            network_metrics=server_spec.network_metrics,
            metrics_id=self.client_id,
            payload_size_mb=model_size_mb,
        )

        # --- Non-Blocking for the Server, happens in parallel Ray workers! ---
        fit_res: FitRes = self.inner_client.fit(ins)
        # ---------------------------------------------------------------------

        t_train = estimate_training_time(
            client_spec=client_spec,
            dataset_size=fit_res.num_examples,
            epochs=epochs,
            model_complexity=model_complexity,
        )

        res_arrays = parameters_to_ndarrays(fit_res.parameters)
        res_size_mb = sum([a.nbytes for a in res_arrays]) / (1024 * 1024)

        t_upload = estimate_transmission_time(
            sender_spec=server_spec,
            receiver_spec=client_spec,
            network_metrics=server_spec.network_metrics,
            metrics_id=self.client_id,
            payload_size_mb=res_size_mb,
        )

        total_virtual_duration = t_download + t_train + t_upload

        if fit_res.metrics is None:
            fit_res.metrics = {}

        fit_res.metrics["simulation_duration"] = total_virtual_duration
        fit_res.metrics["client_id"] = self.client_id
        fit_res.metrics["ref_model_age"] = ref_model_age

        # Return event directly back to Orchestrator to route to Server
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
                        "fit_res": fit_res,
                    },
                },
                None,
            )
        ]
