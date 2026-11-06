"""Model definition, federated data loading, and local PyTorch training."""

# Training/evaluation helpers follow Flower's Apache-2.0 PyTorch quickstart.
# FedSim modifies model architecture, data loading, label handling, and training strategies.
# Source attribution: THIRD_PARTY_NOTICES.md.

import ray
import torch
import torch.nn as nn
import torch.nn.functional as F
from filelock import FileLock
from flwr_datasets import FederatedDataset
from flwr_datasets.partitioner import IidPartitioner
from torch.utils.data import DataLoader
from torchvision.transforms import Compose, Lambda, Normalize, Resize, ToTensor

from fedsim.settings import data_dir, dataset_cache_dir
from fedsim.strategies.client_strategies import get_client_strategy

DEFAULT_DATASET_ID = "uoft-cs/cifar10"


class Net(nn.Module):
    """
    Generalized 3-Conv, 2-FC Model (Spyker Paper spec).
    """

    def __init__(self, num_classes=10):
        super(Net, self).__init__()

        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1)

        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1)

        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1)

        self.pool = nn.MaxPool2d(2, 2)

        # Adaptive pool ensures that if a dataset is  slightly off-size, it is forced to 4x4 before the Linear layers.
        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))

        self.fc1 = nn.Linear(128 * 4 * 4, 256)

        # Fully Connected Layer 2 (Output layer)
        self.fc2 = nn.Linear(256, num_classes)

    def forward(self, x):
        # Support Grayscale to RGB conversion for MNIST/Fashion-MNIST
        if x.shape[1] == 1:
            x = x.repeat(1, 3, 1, 1)

        # 3-Conv block with ReLU activations and Pooling
        x = self.pool(F.relu(self.conv1(x)))
        x = self.pool(F.relu(self.conv2(x)))
        x = self.pool(F.relu(self.conv3(x)))

        # Force feature map to 4x4 for dataset agnosticism
        x = self.adaptive_pool(x)

        x = x.view(-1, 128 * 4 * 4)

        x = F.relu(self.fc1(x))
        return self.fc2(x)


# Resizes everything to 32x32 to maintain consistency for the CNN
generic_transforms = Compose(
    [
        Resize((32, 32)),
        Lambda(lambda img: img.convert("RGB")),
        ToTensor(),
        Normalize((0.5, 0.5, 0.5), (0.5, 0.5, 0.5)),
    ]
)


@ray.remote
class DatasetProvider:
    def __init__(self, dataset_id: str, num_partitions: int, seed: int):
        partitioner = IidPartitioner(num_partitions=num_partitions)
        self.fds = FederatedDataset(
            dataset=dataset_id,
            partitioners={"train": partitioner},
        )
        self.partitions = {}

        for i in range(num_partitions):
            part = self.fds.load_partition(i)
            self.partitions[i] = part.train_test_split(test_size=0.2, seed=seed)

    def get_partition(self, partition_id: int):
        return self.partitions[partition_id]


def preload_dataset(dataset_id: str | None = None):
    """Pre-download the dataset in the backend before engine execution."""

    from datasets import load_dataset

    normalized_dataset_id = (dataset_id or "").strip() or DEFAULT_DATASET_ID
    cache_dir = dataset_cache_dir()
    with FileLock(str(cache_dir / "dataset.lock")):
        print(f"Preloading dataset: {normalized_dataset_id}")
        load_dataset(normalized_dataset_id, cache_dir=str(cache_dir))


def apply_transforms(batch):
    img_key = "img" if "img" in batch else "image"
    batch["img"] = [generic_transforms(img) for img in batch[img_key]]
    return batch


def load_data(
    partition_id: int, num_partitions: int, seed: int | None = None, dataset_id: str | None = None
):
    if partition_id < 0 or partition_id >= num_partitions:
        raise ValueError(
            f"partition_id={partition_id} out of range for num_partitions={num_partitions}"
        )

    normalized_dataset_id = (dataset_id or "").strip() or DEFAULT_DATASET_ID
    split_seed = 42 if seed is None else int(seed)

    safe_id = normalized_dataset_id.replace("/", "_")
    actor_name = f"dataset_provider_{safe_id}_{num_partitions}_{split_seed}"

    try:
        provider = ray.get_actor(actor_name)
    except ValueError:
        lock_dir = data_dir() / "locks"
        lock_dir.mkdir(parents=True, exist_ok=True)
        with FileLock(str(lock_dir / "dataset-provider.lock")):
            try:
                provider = ray.get_actor(actor_name)
            except ValueError:
                provider = DatasetProvider.options(name=actor_name, lifetime="detached").remote(
                    normalized_dataset_id, num_partitions, split_seed
                )

    partition_train_test = ray.get(provider.get_partition.remote(partition_id))

    partition_train_test = partition_train_test.with_transform(apply_transforms)

    generator = None
    if seed is not None:
        generator = torch.Generator()
        generator.manual_seed(int(seed))

    trainloader = DataLoader(
        partition_train_test["train"], batch_size=32, shuffle=True, generator=generator
    )
    testloader = DataLoader(partition_train_test["test"], batch_size=32)

    return trainloader, testloader


def train(net, trainloader, epochs, lr, device, strategy_name="standard"):
    """Train the model on the training set."""
    net.to(device)
    criterion = torch.nn.CrossEntropyLoss().to(device)
    optimizer = torch.optim.SGD(net.parameters(), lr=lr, momentum=0.9, weight_decay=1e-4)

    strategy = get_client_strategy(strategy_name)

    net.train()
    running_loss = 0.0
    for _ in range(epochs):
        for batch in trainloader:
            images = batch["img"].to(device)
            # Handle standard datasets where labels might be under "label" or "labels"
            label_key = "label" if "label" in batch else "labels"
            labels = batch[label_key].to(device)

            optimizer.zero_grad()

            loss = strategy.compute_loss(net, images, labels, criterion)
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
            label_key = "label" if "label" in batch else "labels"
            labels = batch[label_key].to(device)

            outputs = net(images)
            loss += criterion(outputs, labels).item()
            correct += (torch.max(outputs.data, 1)[1] == labels).sum().item()

    accuracy = correct / len(testloader.dataset)
    loss = loss / len(testloader)
    return loss, accuracy
