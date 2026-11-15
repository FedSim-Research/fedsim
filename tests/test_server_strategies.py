import numpy as np
import pytest

from fedsim.strategies.server_strategies import FedAvgSyncStrategy


@pytest.mark.parametrize("groups", [((0, 1), (2, 3)), ((0, 3), (1, 2)), ((0,), (1, 2, 3))])
def test_two_level_fedavg_preserves_the_independent_sample_weighted_result(groups):
    strategy = FedAvgSyncStrategy()
    initial = [np.zeros(2), np.zeros(1)]
    updates = [
        ([np.array([value, 2 * value]), np.array([value + 1])], samples)
        for value, samples in ((0.0, 1), (10.0, 2), (20.0, 3), (30.0, 4))
    ]
    # Independent reference: (1*0 + 2*10 + 3*20 + 4*30) / 10 = 20.
    expected = [np.array([20.0, 40.0]), np.array([21.0])]
    flat = strategy.aggregate(initial, updates)
    edges = []
    for group in groups:
        subset = [updates[index] for index in group]
        edges.append((strategy.aggregate(initial, subset), sum(samples for _, samples in subset)))
    hierarchical = strategy.aggregate(initial, edges)
    for actual in (flat, hierarchical):
        for tensor, reference in zip(actual, expected, strict=True):
            np.testing.assert_allclose(tensor, reference, rtol=0, atol=1e-12)
