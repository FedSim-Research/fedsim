"""Shared checkpoint and periodic model evaluation."""

from typing import Any

import torch
from torch.utils.data import DataLoader
from torchvision.datasets import CIFAR10, MNIST

from fedsim.learning import DEFAULT_DATASET_ID, Net, generic_transforms, test
from fedsim.settings import evaluation_data_dir


class DataLoaderAdapter:
    """Expose torchvision batches in the mapping format used by local training."""

    def __init__(self, loader: DataLoader):
        self.loader = loader
        self.dataset = loader.dataset

    def __iter__(self):
        for images, labels in self.loader:
            yield {"img": images, "label": labels}

    def __len__(self):
        return len(self.loader)


def load_evaluation_data(dataset_id: str, batch_size: int = 64) -> DataLoaderAdapter:
    datasets = {"uoft-cs/cifar10": CIFAR10, "ylecun/mnist": MNIST}
    if dataset_id not in datasets:
        raise ValueError(f"Unsupported evaluation dataset: {dataset_id}")
    dataset = datasets[dataset_id](
        root=str(evaluation_data_dir()),
        train=False,
        download=True,
        transform=generic_transforms,
    )
    return DataLoaderAdapter(DataLoader(dataset, batch_size=batch_size, shuffle=False))


def evaluate_model(filename: str, dataset_id: str = DEFAULT_DATASET_ID) -> dict[str, float]:
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = Net().to(device)
    model.load_state_dict(torch.load(filename, map_location=device, weights_only=True), strict=True)
    loss, accuracy = test(model, load_evaluation_data(dataset_id, batch_size=32), device)
    return {"accuracy": float(accuracy), "avg_loss": float(loss)}


def summarize_server_evaluations(per_server: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Give every server metric equal weight, without averaging model parameters."""
    if not per_server:
        raise ValueError("evaluation_requires_servers")
    count = len(per_server)
    return {
        "accuracy": sum(item["accuracy"] for item in per_server.values()) / count,
        "avg_loss": sum(item["avg_loss"] for item in per_server.values()) / count,
        "aggregation": "server_macro_mean",
        "server_count": count,
        "per_server": per_server,
    }


def evaluate_models(
    filenames: dict[str, str], dataset_id: str = DEFAULT_DATASET_ID
) -> dict[str, Any]:
    """Evaluate every checkpoint on the same loaded, non-shuffled test dataset."""
    if not filenames:
        raise ValueError("evaluation_requires_servers")
    device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
    model = Net().to(device)
    loader = load_evaluation_data(dataset_id, batch_size=32)
    per_server = {}
    for server_id, filename in filenames.items():
        model.load_state_dict(
            torch.load(filename, map_location=device, weights_only=True), strict=True
        )
        loss, accuracy = test(model, loader, device)
        per_server[server_id] = {"accuracy": float(accuracy), "avg_loss": float(loss)}
    return summarize_server_evaluations(per_server)
