from unittest.mock import Mock

import pytest

from fedsim.simulation import compute_model
from fedsim.specs.client_spec import ClientSpec
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec


def duration(kind, compute_factor, sigma):
    performance = Performance(compute_factor, sigma)
    if kind == "training":
        client = ClientSpec("client", "Client", performance, 10, 10)
        return compute_model.estimate_training_time(client, 12, 2, 1)
    server = ServerSpec("server", "Server", performance, {}, 10, 10)
    return compute_model.estimate_aggregation_time(
        server, 3, 8, throughput_bytes_per_second=compute_factor
    )


@pytest.mark.parametrize("kind", ["training", "aggregation"])
def test_zero_sigma_uses_nominal_duration_without_random_draw(monkeypatch, kind):
    noise = Mock(side_effect=AssertionError("Zero sigma must not consume random state"))
    monkeypatch.setattr(compute_model.random, "gauss", noise)
    assert duration(kind, compute_factor=6, sigma=0) == pytest.approx(4.0)
    assert duration(kind, compute_factor=12, sigma=0) == pytest.approx(2.0)


@pytest.mark.parametrize("kind", ["training", "aggregation"])
def test_sigma_is_zero_mean_additive_noise_in_seconds(monkeypatch, kind):
    noise = Mock(return_value=0.25)
    monkeypatch.setattr(compute_model.random, "gauss", noise)
    assert duration(kind, compute_factor=6, sigma=0.5) == pytest.approx(4.25)
    noise.assert_called_once_with(0, 0.5)


@pytest.mark.parametrize("kind", ["training", "aggregation"])
def test_negative_noisy_duration_keeps_positive_floor(monkeypatch, kind):
    monkeypatch.setattr(compute_model.random, "gauss", lambda *args: -10)
    assert duration(kind, compute_factor=6, sigma=1) == pytest.approx(1e-6)


@pytest.mark.parametrize("compute_factor", [2, 10, 1000])
def test_aggregation_uses_separate_input_byte_throughput(compute_factor):
    server = ServerSpec("server", "Server", Performance(compute_factor, 0), {}, 10, 10)
    assert compute_model.estimate_aggregation_time(
        server, 1, 2_481_448, throughput_bytes_per_second=100_000_000
    ) == pytest.approx(0.02481448)
    assert compute_model.estimate_aggregation_time(
        server, 4, 2_481_448, throughput_bytes_per_second=100_000_000
    ) == pytest.approx(4 * 0.02481448)


@pytest.mark.parametrize("value", [None, True, False, 0, -1, float("nan"), float("inf"), "100", []])
def test_aggregation_requires_finite_positive_explicit_throughput(value):
    server = ServerSpec("server", "Server", Performance(2, 0), {}, 10, 10)
    with pytest.raises(ValueError, match="aggregation_throughput"):
        compute_model.estimate_aggregation_time(server, 1, 8, throughput_bytes_per_second=value)
