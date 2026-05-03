from abc import ABC, abstractmethod
from typing import List, Tuple
import numpy as np
import torch

class SyncServerStrategy(ABC):
    """Used by Hierarchical Edge/Super servers to merge batches of updates."""
    @abstractmethod
    def aggregate(self, global_weights: List[np.ndarray], updates: List[Tuple[List[np.ndarray], int]]) -> List[np.ndarray]:
        pass

class AsyncServerStrategy(ABC):
    """Used by Spyker to merge single updates on the fly."""
    @abstractmethod
    def aggregate(self, global_weights: List[np.ndarray], update_weights: List[np.ndarray], alpha: float) -> List[np.ndarray]:
        pass

class ClientTrainingStrategy(ABC):
    """Used by task.py to calculate loss during local training."""
    @abstractmethod
    def compute_loss(self, net: torch.nn.Module, global_net: torch.nn.Module, images: torch.Tensor, labels: torch.Tensor, criterion) -> torch.Tensor:
        pass
