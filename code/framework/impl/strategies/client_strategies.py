from abc import ABC, abstractmethod
import torch

class ClientTrainingStrategy(ABC):
    """Used by task.py to calculate loss during local training."""
    @abstractmethod
    def compute_loss(self, net: torch.nn.Module, images: torch.Tensor, labels: torch.Tensor, criterion) -> torch.Tensor:
        pass

class StandardClientStrategy(ClientTrainingStrategy):
    """Standard SGD Classification Loss used by Spyker and FedAvg."""
    def compute_loss(self, net, images, labels, criterion):
        outputs = net(images)
        return criterion(outputs, labels)

# Factory for the PyTorch Loop
def get_client_strategy(strategy_name: str) -> ClientTrainingStrategy:
    if strategy_name.lower() == "standard":
        return StandardClientStrategy()
    raise ValueError(f"Unknown Client Strategy: {strategy_name}")
