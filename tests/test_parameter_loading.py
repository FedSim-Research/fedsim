import numpy as np
import pytest
import torch

from fedsim.clients.training import TrainingClient


@pytest.mark.parametrize("change", ["missing", "extra", "shape"])
def test_invalid_parameters_leave_the_model_unchanged(change):
    client = TrainingClient(0, 1, seed=42)
    before = {name: value.clone() for name, value in client.net.state_dict().items()}
    incoming = [value.numpy().copy() + 1 for value in before.values()]
    if change == "missing":
        incoming.pop()
    elif change == "extra":
        incoming.append(np.zeros(1, dtype=np.float32))
    else:
        incoming[-1] = np.zeros(1, dtype=np.float32)
    with pytest.raises(ValueError, match="client_parameter_"):
        client.set_parameters(incoming)
    for name, value in client.net.state_dict().items():
        torch.testing.assert_close(value, before[name], rtol=0, atol=0)


def test_valid_readonly_parameter_arrays_keep_copy_semantics():
    client = TrainingClient(0, 1, seed=42)
    incoming = [value.copy() + 1 for value in client.get_parameters()]
    expected = [value.copy() for value in incoming]
    for value in incoming:
        value.flags.writeable = False
    client.set_parameters(incoming)
    for actual, value in zip(client.get_parameters(), expected, strict=True):
        np.testing.assert_array_equal(actual, value)
