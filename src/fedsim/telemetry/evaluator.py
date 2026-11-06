from collections import OrderedDict
from typing import Any, Dict

import ray
import torch

# Import the PyTorch logic from your app
from fedsim.evaluation import load_evaluation_data
from fedsim.learning import Net, test
from fedsim.services.evaluation_point_store import persist_periodic_evaluation
from fedsim.telemetry.logging import setup_telemetry_logger


@ray.remote
class PeriodicEvaluator:
    def __init__(
        self,
        run_id: str,
        graph_id: str,
        architecture: str,
        target_server_ref: ray.ObjectRef,
        orchestrator_ref: ray.ObjectRef,
        evaluation_interval: float,
        dataset: str = "uoft-cs/cifar10",
    ):
        self.run_id = run_id
        self.graph_id = graph_id
        self.architecture = architecture
        self.target_server = target_server_ref
        self.orchestrator = orchestrator_ref
        self.interval = evaluation_interval
        self.dataset_id = dataset

        self.logger = setup_telemetry_logger(self.run_id)

        # Determine device
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        print(f"[{self.architecture} Evaluator] Initializing on {self.device}...")

        # Initialize model
        self.model = Net().to(self.device)

        self.test_loader = load_evaluation_data(self.dataset_id, batch_size=64)

        try:
            self.self_ref = ray.get_runtime_context().current_actor
        except Exception:
            self.self_ref = None

    def start(self):
        """Kicks off the first evaluation at T=0."""
        return self.evaluate({"trigger_time": 0.0})

    def evaluate(self, payload: Dict[str, Any]):
        current_virtual_time = payload.get("trigger_time", 0.0)

        # Fetch current global weights & metrics
        weights_np = ray.get(self.target_server.get_global_model.remote())
        try:
            server_metrics = ray.get(self.target_server.get_metrics.remote())
        except AttributeError:
            server_metrics = {}

        # Load weights & Evaluate
        keys = self.model.state_dict().keys()
        state_dict = OrderedDict({k: torch.tensor(v) for k, v in zip(keys, weights_np)})
        self.model.load_state_dict(state_dict, strict=True)
        avg_loss, accuracy = test(self.model, self.test_loader, self.device)

        # STRICT SCHEMA DEFINITION
        # Extract current round standardizing between Spyker (model_age) and Hierarchical
        round_val = server_metrics.get("model_age", server_metrics.get("current_round", 0))

        extra_data = {
            "log_type": "periodic_evaluation",
            "run_id": self.run_id,
            "graph_id": self.graph_id,
            "architecture": self.architecture,
            "virtual_time": current_virtual_time,
            "round": round_val,
            "accuracy": float(accuracy),
            "loss": float(avg_loss),
            "server_stats": server_metrics,
        }

        self.logger.info("Evaluation Complete", extra={"extra_data": extra_data})
        persist_periodic_evaluation(extra_data)
        print(
            f"[{self.architecture} Eval] run_id={self.run_id} "
            f"T={current_virtual_time:>6.1f}s | Round: {round_val} | "
            f"Acc: {accuracy * 100:>5.2f} | Loss: {avg_loss:.4f}"
        )

        # Schedule Next Evaluation
        if self.self_ref:
            next_payload = {
                "event_type": "EVALUATE",
                "trigger_time": current_virtual_time + self.interval,
            }
            return [(self.interval, self.self_ref, "evaluate", next_payload)]
        return []
