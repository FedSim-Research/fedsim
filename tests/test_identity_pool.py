import pytest
import torch
import torch.nn.functional as F

from fedsim.learning import Net


def test_removing_identity_adaptive_pool_preserves_values_and_gradients():
    generator = torch.Generator().manual_seed(42)
    features = torch.randn(2, 128, 4, 4, generator=generator, requires_grad=True)
    upstream = torch.randn(features.shape, generator=generator)
    reference = F.adaptive_avg_pool2d(features, (4, 4))
    gradient = torch.autograd.grad(reference, features, upstream)[0]
    torch.testing.assert_close(reference, features, rtol=0, atol=0)
    torch.testing.assert_close(gradient, upstream, rtol=0, atol=0)


@pytest.mark.parametrize(("side", "expected_pool_calls"), [(32, 0), (64, 1)])
def test_net_skips_only_identity_adaptation_and_retains_other_input_sizes(
    side, expected_pool_calls
):
    model = Net(seed=42)
    calls = []
    handle = model.adaptive_pool.register_forward_hook(lambda *args: calls.append(True))
    try:
        outputs = model(torch.zeros(2, 3, side, side))
        outputs.sum().backward()
    finally:
        handle.remove()
    assert outputs.shape == (2, 10)
    assert len(calls) == expected_pool_calls
    assert all(
        parameter.grad is not None and torch.isfinite(parameter.grad).all()
        for parameter in model.parameters()
    )
