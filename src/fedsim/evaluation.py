"""Shared checkpoint and periodic model evaluation."""

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
