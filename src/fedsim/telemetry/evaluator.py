from collections import OrderedDict
from typing import Any, Dict

import ray
import torch

from fedsim.evaluation import load_evaluation_data, summarize_server_evaluations
from fedsim.learning import Net, test
from fedsim.services.evaluation_point_store import persist_periodic_evaluation
from fedsim.telemetry.logging import setup_telemetry_logger


@ray.remote(num_cpus=0, num_gpus=0)
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
        target_servers: dict[str, Any] | None = None,
    ):
        if target_servers is not None and not target_servers:
            raise ValueError("evaluation_requires_servers")
        self.run_id = run_id
        self.graph_id = graph_id
        self.architecture = architecture
        self.target_server = target_server_ref
        self.target_servers = target_servers
        self.orchestrator = orchestrator_ref
        self.interval = evaluation_interval
        self.dataset_id = dataset
        torch.set_num_threads(1)

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

        targets = (
            self.target_servers if self.target_servers is not None else {"": self.target_server}
        )
        # Queue all snapshot requests before evaluating. Each actor supplies its
        # weights and progress in one call; this is not a cross-server barrier.
        snapshots = ray.get([actor.get_evaluation_snapshot.remote() for actor in targets.values()])
        per_server = {}
        for server_id, snapshot in zip(targets, snapshots, strict=True):
            keys = self.model.state_dict().keys()
            state = OrderedDict(
                {
                    key: torch.tensor(value)
                    for key, value in zip(keys, snapshot["parameters"], strict=True)
                }
            )
            self.model.load_state_dict(state, strict=True)
            avg_loss, accuracy = test(self.model, self.test_loader, self.device)
            metrics = snapshot["metrics"]
            per_server[server_id] = {
                "accuracy": float(accuracy),
                "avg_loss": float(avg_loss),
                "round": metrics.get("model_age", metrics.get("current_round", 0)),
                "snapshot_virtual_time": snapshot["virtual_time"],
                "server_stats": metrics,
            }

        if self.target_servers is None:
            single = per_server[""]
            accuracy, avg_loss = single["accuracy"], single["avg_loss"]
            round_val, server_metrics = single["round"], single["server_stats"]
        else:
            summary = summarize_server_evaluations(per_server)
            accuracy, avg_loss = summary["accuracy"], summary["avg_loss"]
            round_val = min(item["round"] for item in per_server.values())
            server_metrics = {
                "aggregation": summary["aggregation"],
                "server_count": summary["server_count"],
                "per_server": per_server,
                "round_aggregation": "minimum_model_age",
            }

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
