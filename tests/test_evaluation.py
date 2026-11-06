import numpy as np
import pytest
import torch
from torch.utils.data import TensorDataset

from fedsim import evaluation
from fedsim.clients.training import TrainingClient
from fedsim.learning import Net
from fedsim.strategies.server_strategies import FedAvgSyncStrategy


@pytest.mark.parametrize("dataset_id", ["uoft-cs/cifar10", "ylecun/mnist"])
def test_checkpoint_evaluation_uses_shared_loader_without_downloading(
    monkeypatch, tmp_path, dataset_id
):
    inputs = torch.zeros((3, 3, 32, 32))
    labels = torch.zeros(3, dtype=torch.long)
    dataset = TensorDataset(inputs, labels)
    calls = []

    def fake_dataset(**kwargs):
        calls.append(kwargs)
        return dataset

    monkeypatch.setattr(evaluation, "CIFAR10", fake_dataset)
    monkeypatch.setattr(evaluation, "MNIST", fake_dataset)
    monkeypatch.setattr(torch.cuda, "is_available", lambda: False)
    checkpoint = tmp_path / "model.pth"
    torch.save(Net().state_dict(), checkpoint)

    result = evaluation.evaluate_model(str(checkpoint), dataset_id)
    assert set(result) == {"accuracy", "avg_loss"}
    assert 0 <= result["accuracy"] <= 1
    assert np.isfinite(result["avg_loss"])
    assert calls[0]["train"] is False
    assert calls[0]["root"].endswith("datasets")
    batches = list(evaluation.load_evaluation_data(dataset_id, batch_size=2))
    assert [len(batch["label"]) for batch in batches] == [2, 1]


def test_client_parameter_round_trip_requires_no_flower_framework():
    client = TrainingClient(partition_id=0, num_partitions=2)
    parameters = client.get_parameters()
    changed = [np.full_like(parameter, 0.125) for parameter in parameters]
    client.set_parameters(changed)
    for actual, expected in zip(client.get_parameters(), changed, strict=True):
        np.testing.assert_array_equal(actual, expected)
    assert not hasattr(client, "trainloader")


def test_fedavg_preserves_sample_weighting():
    result = FedAvgSyncStrategy().aggregate(
        [np.array([0.0, 0.0])],
        [([np.array([1.0, 5.0])], 1), ([np.array([5.0, 1.0])], 3)],
    )
    np.testing.assert_allclose(result[0], [4.0, 2.0])
