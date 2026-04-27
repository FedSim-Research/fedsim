"""impl: A Flower / PyTorch app."""

import ray
import torch
import torch.nn as nn
import torch.nn.functional as F
from threading import Lock
from filelock import FileLock
from flwr_datasets import FederatedDataset
from flwr_datasets.partitioner import IidPartitioner
from torch.utils.data import DataLoader
from torchvision.transforms import Compose, Normalize, ToTensor


DEFAULT_DATASET_ID = "uoft-cs/cifar10"


class Net(nn.Module):
    """Model (simple CNN adapted from 'PyTorch: A 60 Minute Blitz')"""

    def __init__(self):
        super(Net, self).__init__()
        self.conv1 = nn.Conv2d(3, 6, 5)
        self.pool = nn.MaxPool2d(2, 2)
        self.conv2 = nn.Conv2d(6, 16, 5)
        self.fc1 = nn.Linear(16 * 5 * 5, 120)
        self.fc2 = nn.Linear(120, 84)
        self.fc3 = nn.Linear(84, 10)

    def forward(self, x):
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = x.view(-1, 16 * 5 * 5)
        x = F.relu(self.fc1(x))
        x = F.relu(self.fc2(x))
        return self.fc3(x)


pytorch_transforms = Compose([ToTensor(), Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5))])


@ray.remote
class DatasetProvider:
    def __init__(self, dataset_id: str, num_partitions: int, seed: int):
        partitioner = IidPartitioner(num_partitions=num_partitions)
        self.fds = FederatedDataset(
            dataset=dataset_id,
            partitioners={"train": partitioner},
        )
        self.partitions = {}

        # Pre-partition to do all disk/HF work once!
        for i in range(num_partitions):
            part = self.fds.load_partition(i)
            self.partitions[i] = part.train_test_split(test_size=0.2, seed=seed)

    def get_partition(self, partition_id: int):
        return self.partitions[partition_id]


def preload_dataset(dataset_id: str | None = None):
    """Pre-download the dataset in the backend before engine execution."""
    from datasets import load_dataset
    import os

    normalized_dataset_id = (dataset_id or "").strip() or DEFAULT_DATASET_ID

    os.makedirs("/hf-cache/datasets", exist_ok=True)
    with FileLock("/hf-cache/datasets/hf_dataset.lock"):
        print(f"Preloading dataset: {normalized_dataset_id}")
        load_dataset(normalized_dataset_id)


def apply_transforms(batch):
    """Apply transforms to the partition from FederatedDataset."""
    batch["img"] = [pytorch_transforms(img) for img in batch["img"]]
    return batch


def load_data(
    partition_id: int,
    num_partitions: int,
    seed: int | None = None,
    dataset_id: str | None = None,
):
    """Load one partition for the selected dataset utilizing a centralized Ray Actor."""
    if partition_id < 0 or partition_id >= num_partitions:
        raise ValueError(
            f"partition_id={partition_id} out of range for num_partitions={num_partitions}"
        )

    normalized_dataset_id = (dataset_id or "").strip() or DEFAULT_DATASET_ID
    split_seed = 42 if seed is None else int(seed)

    # Create a unique name for this actor based on the dataset config
    safe_id = normalized_dataset_id.replace("/", "_")
    actor_name = f"dataset_provider_{safe_id}_{num_partitions}_{split_seed}"

    # 1. Connect to or create the global DatasetProvider
    try:
        provider = ray.get_actor(actor_name)
    except ValueError:
        # Use FileLock just to prevent race conditions while Spawning the single Ray Actor
        with FileLock("ray_provider.lock"):
            try:
                provider = ray.get_actor(actor_name)
            except ValueError:
                provider = DatasetProvider.options(
                    name=actor_name, lifetime="detached"
                ).remote(normalized_dataset_id, num_partitions, split_seed)

    # 2. Fetch the pre-processed data split directly from the central actor
    # Ray natively understands PyArrow (which HF Datasets use) and will transfer this instantly.
    partition_train_test = ray.get(provider.get_partition.remote(partition_id))

    # 3. Apply transformations and build DataLoaders locally on the client
    partition_train_test = partition_train_test.with_transform(apply_transforms)

    generator = None
    if seed is not None:
        generator = torch.Generator()
        generator.manual_seed(int(seed))

    trainloader = DataLoader(
        partition_train_test["train"],
        batch_size=32,
        shuffle=True,
        generator=generator,
    )
    testloader = DataLoader(partition_train_test["test"], batch_size=32)

    return trainloader, testloader


def train(net, trainloader, epochs, lr, device):
    """Train the model on the training set."""
    net.to(device)  # move model to GPU if available
    criterion = torch.nn.CrossEntropyLoss().to(device)
    optimizer = torch.optim.Adam(net.parameters(), lr=lr)
    net.train()
    running_loss = 0.0
    for _ in range(epochs):
        for batch in trainloader:
            images = batch["img"].to(device)
            labels = batch["label"].to(device)
            optimizer.zero_grad()
            loss = criterion(net(images), labels)
            loss.backward()
            optimizer.step()
            running_loss += loss.item()
    avg_trainloss = running_loss / len(trainloader)
    return avg_trainloss


def test(net, testloader, device):
    """Validate the model on the test set."""
    net.to(device)
    net.eval()
    criterion = torch.nn.CrossEntropyLoss()
    correct, loss = 0, 0.0
    with torch.no_grad():
        for batch in testloader:
            images = batch["img"].to(device)
            labels = batch["label"].to(device)
            outputs = net(images)
            loss += criterion(outputs, labels).item()
            correct += (torch.max(outputs.data, 1)[1] == labels).sum().item()
    accuracy = correct / len(testloader.dataset)
    loss = loss / len(testloader)
    return loss, accuracy
