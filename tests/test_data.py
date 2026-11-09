import math

import numpy as np
import pytest
import torch
from datasets import Dataset
from flwr_datasets.partitioner import IidPartitioner
from PIL import Image
from torch.utils.data import DataLoader

from fedsim.learning import Net, apply_transforms, train


def image_dataset(size=12):
    return Dataset.from_dict(
        {
            "sample_id": list(range(size)),
            "img": [Image.new("RGB", (32, 32), (index * 10, 20, 30)) for index in range(size)],
            "label": [index % 2 for index in range(size)],
        }
    )


def test_flower_iid_partitions_cover_local_dataset_without_overlap():
    partitioner = IidPartitioner(num_partitions=3)
    partitioner.dataset = image_dataset()
    partitions = [set(partitioner.load_partition(index)["sample_id"]) for index in range(3)]
    assert [len(partition) for partition in partitions] == [4, 4, 4]
    assert set.union(*partitions) == set(range(12))
    assert sum(len(partition) for partition in partitions) == len(set.union(*partitions))


@pytest.mark.parametrize("image_column", ["img", "image"])
def test_huggingface_image_batches_train_with_current_pytorch(image_column):
    dataset = image_dataset(size=4)
    if image_column != "img":
        dataset = dataset.rename_column("img", image_column)
    dataset = dataset.with_transform(apply_transforms)
    loader = DataLoader(dataset, batch_size=4, shuffle=False)
    batch = next(iter(loader))
    assert batch["img"].shape == (4, 3, 32, 32)
    assert "image" not in batch
    assert batch["label"].dtype == torch.int64
    model = Net()
    before = model.fc2.weight.detach().numpy().copy()
    loss = train(model, loader, epochs=1, lr=0.01, device=torch.device("cpu"))
    assert math.isfinite(loss)
    assert not np.array_equal(before, model.fc2.weight.detach().numpy())
