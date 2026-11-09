"""Model definition, federated data loading, and local PyTorch training."""

# Training/evaluation helpers follow Flower's Apache-2.0 PyTorch quickstart.
# FedSim modifies model architecture, data loading, label handling, and training strategies.
# Source attribution: THIRD_PARTY_NOTICES.md.

import hashlib
import json
import math

import ray
import torch
import torch.nn as nn
import torch.nn.functional as F
from filelock import FileLock
from flwr_datasets import FederatedDataset
from flwr_datasets.partitioner import IidPartitioner
from torch.utils.data import DataLoader
from torchvision.transforms import Compose, Lambda, Normalize, Resize, ToTensor

from fedsim.settings import dataset_cache_dir
from fedsim.simulation.randomness import derive_seed
from fedsim.strategies.client_strategies import get_client_strategy

DEFAULT_DATASET_ID = "uoft-cs/cifar10"


class Net(nn.Module):
    """
    Generalized 3-Conv, 2-FC model with a private CPU initialization generator.
    """

    def __init__(self, num_classes=10, *, seed: int | None = None):
        super(Net, self).__init__()

        # Meta construction avoids consuming PyTorch's process-global generator.
        self.conv1 = nn.Conv2d(3, 32, kernel_size=3, padding=1, device="meta")

        self.conv2 = nn.Conv2d(32, 64, kernel_size=3, padding=1, device="meta")

        self.conv3 = nn.Conv2d(64, 128, kernel_size=3, padding=1, device="meta")

        self.pool = nn.MaxPool2d(2, 2)

        # Adaptive pool ensures that if a dataset is  slightly off-size, it is forced to 4x4 before the Linear layers.
        self.adaptive_pool = nn.AdaptiveAvgPool2d((4, 4))

        self.fc1 = nn.Linear(128 * 4 * 4, 256, device="meta")

        # Fully Connected Layer 2 (Output layer)
        self.fc2 = nn.Linear(256, num_classes, device="meta")

        layers = (self.conv1, self.conv2, self.conv3, self.fc1, self.fc2)
        initialized_parameters = {
            id(parameter)
            for layer in layers
            for parameter in (layer.weight, layer.bias)
            if parameter is not None
        }
        # to_empty discards all state. Refuse extensions without an initializer,
        # including buffers such as BatchNorm running statistics.
        if (
            initialized_parameters != {id(parameter) for parameter in self.parameters()}
            or next(self.buffers(), None) is not None
        ):
            raise RuntimeError("net_initialization_requires_complete_parameter_and_buffer_coverage")

        self.to_empty(device="cpu")
        generator = torch.Generator(device="cpu")
        if seed is None:
            generator.seed()
        else:
            generator.manual_seed(int(seed))
        # Match Conv2d/Linear's default initialization, using only our generator.
        for layer in layers:
            nn.init.kaiming_uniform_(layer.weight, a=math.sqrt(5), generator=generator)
            fan_in = layer.weight[0].numel()
            bound = 1 / math.sqrt(fan_in)
            if layer.bias is not None:
                nn.init.uniform_(layer.bias, -bound, bound, generator=generator)

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


@ray.remote(num_cpus=0, num_gpus=0)
class DatasetProvider:
    def __init__(self, dataset_id: str, num_partitions: int, seed: int):
        self.num_partitions = num_partitions
        self.seed = seed
        partitioner = IidPartitioner(num_partitions=num_partitions)
        self.fds = FederatedDataset(
            dataset=dataset_id,
            partitioners={"train": partitioner},
            shuffle=True,
            seed=seed,
            cache_dir=str(dataset_cache_dir()),
        )
        self.partitions = {}

    def get_partition(self, partition_id: int):
        if not 0 <= partition_id < self.num_partitions:
            raise ValueError("dataset_partition_id_out_of_range")
        if partition_id not in self.partitions:
            part = self.fds.load_partition(partition_id)
            split_seed = derive_seed(self.seed, "data", "split", str(partition_id))
            self.partitions[partition_id] = part.train_test_split(test_size=0.2, seed=split_seed)
        return self.partitions[partition_id]


def dataset_provider_name(
    dataset_id: str, num_partitions: int, partition_seed: int, job_id: str
) -> str:
    """Identify a job-local IID assignment independently of client shuffle seeds."""
    definition = json.dumps(
        ["fedsim-iid-v1", dataset_id, num_partitions, partition_seed],
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"fedsim-dataset-{job_id}-" + hashlib.sha256(definition.encode("utf-8")).hexdigest()


def get_dataset_provider(
    dataset_id: str | None, num_partitions: int, partition_seed: int | None = None
):
    """Create/reuse a job-owned provider; engines call this from the driver."""
    if num_partitions < 1:
        raise ValueError("dataset_requires_positive_partition_count")
    normalized_dataset_id = (dataset_id or "").strip() or DEFAULT_DATASET_ID
    data_seed = 42 if partition_seed is None else int(partition_seed)
    job_id = str(ray.get_runtime_context().get_job_id())
    name = dataset_provider_name(normalized_dataset_id, num_partitions, data_seed, job_id)
    return DatasetProvider.options(name=name, get_if_exists=True, lifetime="non_detached").remote(
        normalized_dataset_id, num_partitions, data_seed
    )


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
    # Remove the source alias so the loader does not also collate raw PIL images.
    images = batch.pop(img_key)
    batch["img"] = [generic_transforms(img) for img in images]
    return batch


def load_data(
    partition_id: int,
    num_partitions: int,
    seed: int | None = None,
    dataset_id: str | None = None,
    *,
    partition_seed: int | None = None,
    dataset_provider=None,
):
    """Load one shared partition; seed controls only the training-loader shuffle."""
    if partition_id < 0 or partition_id >= num_partitions:
        raise ValueError(
            f"partition_id={partition_id} out of range for num_partitions={num_partitions}"
        )

    provider = dataset_provider
    if provider is None:
        provider = get_dataset_provider(dataset_id, num_partitions, partition_seed)
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
    num_examples = 0
    with torch.no_grad():
        for batch in testloader:
            images = batch["img"].to(device)
            label_key = "label" if "label" in batch else "labels"
            labels = batch[label_key].to(device)

            outputs = net(images)
            loss += criterion(outputs, labels).item() * len(labels)
            correct += (torch.max(outputs.data, 1)[1] == labels).sum().item()
            num_examples += len(labels)

    if not num_examples:
        raise ValueError("evaluation_requires_examples")
    accuracy = correct / num_examples
    loss = loss / num_examples
    return loss, accuracy
