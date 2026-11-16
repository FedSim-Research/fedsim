import numpy as np
import pytest

from fedsim.engines.spyker.server import SpykerServer
from fedsim.simulation.context import SimulationContext
from fedsim.simulation.spyker_config import FullConfiguration
from fedsim.specs.performance_metrics import Performance
from fedsim.specs.server_spec import ServerSpec
from fedsim.strategies.server_strategies import SpykerDefaultAsyncStrategy


@pytest.fixture
def make_server(local_actor, monkeypatch):
    def make(**spyker):
        config = FullConfiguration()
        for key, value in spyker.items():
            setattr(config.spyker, key, value)
        specs = {"A": ServerSpec("A", "A", Performance(10, 0), {}, 1000, 1000)}
        context = SimulationContext("orchestrator", {}, specs)
        server = local_actor(SpykerServer, "A", config, context)
        server.set_orchestrator("orchestrator")
        server.set_initial_weights([np.array([10.0])])
        monkeypatch.setattr(server, "_schedule_client_task", lambda client_id: None)
        return server

    return make


def update(server, value, ref_age):
    server.on_client_update(
        {"client_id": "c", "metrics": {"ref_model_age": ref_age}}, [np.array([value])]
    )
    return float(server.get_global_model()[0][0])


def test_default_decay_is_absolute(make_server):
    server = make_server()
    assert server._calculate_decay(3, 2.5, 0.01) == pytest.approx(1e-6)
    assert server._calculate_decay(2, 2.5, 0.01) == 0.01


def test_relative_decay_scales_penalty_with_base_rate(make_server):
    server = make_server(decay_mode="relative")
    assert server._calculate_decay(3, 2.5, 0.01) == pytest.approx(0.01 * (1 - 0.05 * 0.5))
    assert server._calculate_decay(100, 2.5, 0.01) == pytest.approx(1e-6)


def test_unknown_decay_mode_is_rejected(make_server):
    with pytest.raises(ValueError, match="decay_mode"):
        make_server(decay_mode="exponential")._calculate_decay(3, 2.5, 0.01)


def test_default_staleness_is_reciprocal(make_server):
    server = make_server()
    server.model_age = 3
    assert update(server, 20.0, ref_age=0) == pytest.approx(10 + 0.6 / 4 * 10)


def test_no_staleness_blends_with_server_rate(make_server):
    server = make_server(staleness_mode="none")
    server.model_age = 3
    assert update(server, 20.0, ref_age=0) == pytest.approx(16.0)


def test_delta_staleness_applies_only_the_client_change(make_server):
    server = make_server(staleness_mode="delta")
    server.model_age = 1
    server._sent_weights["c"] = [np.array([4.0])]
    # The client returns its unchanged starting model: no pull towards the old state.
    assert update(server, 4.0, ref_age=0) == pytest.approx(10.0)
    assert "c" not in server._sent_weights


def test_aggregate_delta():
    result = SpykerDefaultAsyncStrategy().aggregate_delta(
        [np.array([1.0, 2.0])], [np.array([3.0, 3.0])], [np.array([1.0, 1.0])], alpha=0.5
    )
    np.testing.assert_allclose(result[0], [2.0, 3.0])
