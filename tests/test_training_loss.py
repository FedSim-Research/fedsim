import copy

import pytest
import torch
from torch.nn import functional as F

from fedsim.learning import train


@pytest.mark.parametrize("epochs", [1, 2, 3])
def test_training_loss_is_example_mean_independent_of_epoch_count(epochs):
    model = torch.nn.Linear(2, 2)
    with torch.no_grad():
        model.weight.zero_()
        model.bias.copy_(torch.tensor([2.0, -1.0]))
    images = torch.ones(4, 2)
    labels = torch.tensor([0, 0, 0, 1])
    batches = [
        {"img": images[:3], "label": labels[:3]},
        {"img": images[3:], "label": labels[3:]},
    ]
    expected = F.cross_entropy(model(images), labels).item()
    result = train(copy.deepcopy(model), batches, epochs, 0.0, "cpu")
    assert result == pytest.approx(expected)


def test_training_rejects_loader_without_examples():
    with pytest.raises(ValueError, match="training_requires_examples"):
        train(torch.nn.Linear(2, 2), [], 1, 0.01, "cpu")
