from abc import ABC, abstractmethod
from typing import List, Tuple

import numpy as np


# --- SYNC STRATEGIES (For Hierarchical Engine) ---
class SyncServerStrategy(ABC):
    """Used by Hierarchical Edge/Super servers to merge batches of updates."""

    @abstractmethod
    def aggregate(
        self, global_weights: List[np.ndarray], updates: List[Tuple[List[np.ndarray], int]]
    ) -> List[np.ndarray]:
        pass


class FedAvgSyncStrategy(SyncServerStrategy):
    """Standard Federated Averaging (HierFAVG baseline)."""

    def aggregate(
        self, global_weights: List[np.ndarray], updates: List[Tuple[List[np.ndarray], int]]
    ) -> List[np.ndarray]:
        total_samples = sum(n for _, n in updates)
        if total_samples == 0:
            return global_weights

        weighted_sum = [np.zeros_like(w) for w in global_weights]
        for w, n in updates:
            for i in range(len(w)):
                weighted_sum[i] += w[i] * n

        return [ws / total_samples for ws in weighted_sum]


# --- ASYNC STRATEGIES (For Spyker Engine) ---
class AsyncServerStrategy(ABC):
    """Used by Spyker to merge single updates on the fly."""

    @abstractmethod
    def aggregate(
        self, global_weights: List[np.ndarray], update_weights: List[np.ndarray], alpha: float
    ) -> List[np.ndarray]:
        pass

    @abstractmethod
    def aggregate_delta(
        self,
        global_weights: List[np.ndarray],
        update_weights: List[np.ndarray],
        base_weights: List[np.ndarray],
        alpha: float,
    ) -> List[np.ndarray]:
        """Apply alpha times the client's change relative to the model it trained on."""


class SpykerDefaultAsyncStrategy(AsyncServerStrategy):
    """Standard Spyker Exponential Moving Average."""

    def aggregate(
        self, global_weights: List[np.ndarray], update_weights: List[np.ndarray], alpha: float
    ) -> List[np.ndarray]:
        return [
            w_base + alpha * (w_upd - w_base)
            for w_base, w_upd in zip(global_weights, update_weights)
        ]

    def aggregate_delta(
        self,
        global_weights: List[np.ndarray],
        update_weights: List[np.ndarray],
        base_weights: List[np.ndarray],
        alpha: float,
    ) -> List[np.ndarray]:
        return [
            w_glob + alpha * (w_upd - w_sent)
            for w_glob, w_upd, w_sent in zip(
                global_weights, update_weights, base_weights, strict=True
            )
        ]


# Factories for the Ray Actors
def get_sync_server_strategy(strategy_name: str) -> SyncServerStrategy:
    if strategy_name.lower() == "fedavg":
        return FedAvgSyncStrategy()
    raise ValueError(f"Unknown Sync Server Strategy: {strategy_name}")


def get_async_server_strategy(strategy_name: str) -> AsyncServerStrategy:
    if strategy_name.lower() == "spyker":
        return SpykerDefaultAsyncStrategy()
    raise ValueError(f"Unknown Async Server Strategy: {strategy_name}")
