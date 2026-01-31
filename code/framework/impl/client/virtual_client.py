import flwr
from flwr.common import (
    FitIns,
    FitRes,
    GetParametersIns,
    GetParametersRes,
    EvaluateIns,
    EvaluateRes,
    parameters_to_ndarrays,
)

from simulation.context import get_global_context
from simulation.compute_model import estimate_training_time
from simulation.network_model import estimate_transmission_time


class VirtualClient(flwr.client.Client):
    def __init__(self, client_id: str, inner_client: flwr.client.Client):
        self.client_id = client_id
        self.inner_client = inner_client

    def get_parameters(self, ins: GetParametersIns) -> GetParametersRes:
        return self.inner_client.get_parameters(ins)

    def fit(self, ins: FitIns) -> FitRes:
        """
        Intercepts the training instruction to calculate Virtual Time.
        """
        ctx = get_global_context()
        client_spec = ctx.get_client_spec(self.client_id)

        config = ins.config
        server_id = str(config.get("server_id"))
        epochs = int(config.get("epochs", 1))
        model_complexity = float(config.get("model_complexity", 1.0))
        ref_model_age = config.get("model_age", 0)

        server_spec = ctx.get_server_spec(server_id)

        param_arrays = parameters_to_ndarrays(ins.parameters)
        model_size_bytes = sum([a.nbytes for a in param_arrays])
        model_size_mb = model_size_bytes / (1024 * 1024)

        t_download = estimate_transmission_time(
            sender_spec=server_spec,
            receiver_spec=client_spec,
            network_metrics=server_spec.network_metrics,
            metrics_id=self.client_id,
            payload_size_mb=model_size_mb,
        )

        fit_res: FitRes = self.inner_client.fit(ins)
        t_train = estimate_training_time(
            client_spec=client_spec,
            dataset_size=fit_res.num_examples,
            epochs=epochs,
            model_complexity=model_complexity,
        )

        res_arrays = parameters_to_ndarrays(fit_res.parameters)
        res_size_bytes = sum([a.nbytes for a in res_arrays])
        res_size_mb = res_size_bytes / (1024 * 1024)

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

        return fit_res

    def evaluate(self, ins: EvaluateIns) -> EvaluateRes:
        ctx = get_global_context()
        client_spec = ctx.get_client_spec(self.client_id)

        config = ins.config
        server_id = str(config.get("server_id"))
        inference = 0.3  # usually lower than training
        model_complexity = float(config.get("model_complexity", inference))
        server_spec = ctx.get_server_spec(server_id)

        param_arrays = parameters_to_ndarrays(ins.parameters)
        model_size_mb = sum([a.nbytes for a in param_arrays]) / (1024 * 1024)

        t_download = estimate_transmission_time(
            sender_spec=server_spec,
            receiver_spec=client_spec,
            network_metrics=server_spec.network_metrics,
            metrics_id=self.client_id,
            payload_size_mb=model_size_mb,
        )

        eval_res = self.inner_client.evaluate(ins)

        t_eval = estimate_training_time(
            client_spec,
            eval_res.num_examples,
            epochs=1,
            model_complexity=model_complexity,
        )

        res_arrays = parameters_to_ndarrays(eval_res.parameters)
        res_size_bytes = sum([a.nbytes for a in res_arrays])
        res_size_mb = res_size_bytes / (1024 * 1024)

        t_upload = estimate_transmission_time(
            sender_spec=server_spec,
            receiver_spec=client_spec,
            network_metrics=server_spec.network_metrics,
            metrics_id=self.client_id,
            payload_size_mb=res_size_mb,
        )

        total_virtual_duration = t_download + t_eval + t_upload

        if eval_res.metrics is None:
            eval_res.metrics = {}
        eval_res.metrics["simulation_duration"] = total_virtual_duration

        return eval_res
