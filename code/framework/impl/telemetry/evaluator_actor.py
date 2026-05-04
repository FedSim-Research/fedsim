import ray
import torch
from collections import OrderedDict
from typing import Dict, Any
from torch.utils.data import DataLoader
from torchvision.datasets import CIFAR10
from torchvision.datasets import MNIST

# Import the PyTorch logic from your app
from main.task import Net, test, generic_transforms
from telemetry.logger import setup_telemetry_logger
from backend.services.evaluation_point_store import persist_periodic_evaluation

class DataLoaderAdapter:
    """Wraps standard torchvision DataLoader to match Flower's FederatedDataset dict format."""
    def __init__(self, loader: DataLoader):
        self.loader = loader
        self.dataset = loader.dataset

    def __iter__(self):
        for images, labels in self.loader:
            yield {"img": images, "label": labels}

    def __len__(self):
        return len(self.loader)

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
        dataset: str = "uoft-cs/cifar10"
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
        
        # Load Global Test Set (Cached locally on this worker)
        if self.dataset_id == "uoft-cs/cifar10":
            test_set = CIFAR10(root="./data", train=False, download=True, transform=generic_transforms)
        elif self.dataset_id == "ylecun/mnist":
            test_set = MNIST(root="./data", train=False, download=True, transform=generic_transforms)
        else:
            print(f"Error: Dataset {self.dataset_id} is not yet compatible with testing. Currently supported:\n\t-uoft-cs/cifar10\n\t- ylecun/mnist")
            raise ValueError(f"Dataset {self.dataset_id} is not yet compatible with testing. Currently supported:\n\t-uoft-cs/cifar10\n\t- ylecun/mnist")
            
        self.test_loader = DataLoaderAdapter(DataLoader(test_set, batch_size=64, shuffle=False))
        
        try:
            self.self_ref = ray.get_runtime_context().current_actor
            print(f"[{self.architecture} Evaluator] Successfully obtained self_ref")
        except Exception as e:
            print(f"[{self.architecture} Evaluator] WARNING: Could not obtain self_ref: {e}")
            print(f"[{self.architecture} Evaluator] This means periodic evaluations will NOT be scheduled!")
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
            "server_stats": server_metrics
        }
        
        self.logger.info("Evaluation Complete", extra={"extra_data": extra_data})
        
        # Persist evaluation to database
        try:
            persist_periodic_evaluation(extra_data)
            print(
                f"[{self.architecture} Eval] run_id={self.run_id} "
                f"T={current_virtual_time:>6.1f}s | Round: {round_val} | "
                f"Acc: {accuracy*100:>5.2f} | Loss: {avg_loss:.4f}"
            )
        except Exception as e:
            print(
                f"[{self.architecture} Evaluator] ERROR: Failed to persist evaluation: {e}"
            )
            self.logger.error(f"persist_periodic_evaluation failed: {e}", extra={"extra_data": extra_data})

        # Schedule Next Evaluation
        if self.self_ref:
            next_payload = {"event_type": "EVALUATE", "trigger_time": current_virtual_time + self.interval}
            return [
                (self.interval, self.self_ref, "evaluate", next_payload)
            ]
        else:
            print(f"[{self.architecture} Evaluator] WARNING: self_ref is None, cannot schedule next evaluation")
        return []
