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
    def make(run_id=None, **spyker):
        config = FullConfiguration()
        for key, value in spyker.items():
            setattr(config.spyker, key, value)
        specs = {"A": ServerSpec("A", "A", Performance(10, 0), {}, 1000, 1000)}
        context = SimulationContext("orchestrator", {}, specs)
        server = local_actor(SpykerServer, "A", config, context, run_id=run_id)
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


def test_relative_staleness_measures_drift_in_client_waves(make_server):
    server = make_server(staleness_mode="relative")
    server.assigned_client_instances = dict.fromkeys("abcd")
    assert server._staleness_weight(4) == pytest.approx(0.5)
    assert server._staleness_weight(-2) == 1.0


def test_unknown_staleness_mode_is_rejected(make_server):
    with pytest.raises(ValueError, match="staleness_mode"):
        make_server(staleness_mode="linear")._staleness_weight(1)


def test_sample_weighting_is_off_by_default(make_server):
    assert make_server()._sample_weight("c", 400) == 1.0


def test_sample_weighting_uses_share_of_reporting_clients(make_server):
    server = make_server(sample_weighting=True)
    assert server._sample_weight("a", 100) == 1.0
    assert server._sample_weight("b", 300) == pytest.approx(1.5)


def test_sample_weighted_blend_never_overshoots_client_model(make_server):
    server = make_server(staleness_mode="none", sample_weighting=True)
    server._client_num_examples = {"x": 10}
    server.on_client_update(
        {"client_id": "c", "num_examples": 1000, "metrics": {"ref_model_age": 0}},
        [np.array([20.0])],
    )
    assert float(server.get_global_model()[0][0]) == pytest.approx(20.0)


def test_aggregate_delta():
    result = SpykerDefaultAsyncStrategy().aggregate_delta(
        [np.array([1.0, 2.0])], [np.array([3.0, 3.0])], [np.array([1.0, 1.0])], alpha=0.5
    )
    np.testing.assert_allclose(result[0], [2.0, 3.0])


def test_delta_staleness_survives_overlapping_dispatch(make_server, monkeypatch):
    server = make_server(staleness_mode="delta")
    monkeypatch.undo()
    monkeypatch.setattr(server.__class__, "_schedule_event", lambda *a, **k: None, raising=False)
    server.assigned_client_instances = {"c": object()}
    server.model_age = 1
    server._schedule_client_task("c")
    server.global_model_weights = [np.array([4.0])]
    server._cached_global_weights_ref = None
    server._schedule_client_task("c")
    assert update(server, 4.0, ref_age=0) == pytest.approx(4.0)


class ListLogger:
    def __init__(self):
        self.records = []

    def info(self, message, extra):
        self.records.append(extra["extra_data"])


@pytest.fixture
def trace_logger(monkeypatch):
    logger = ListLogger()
    monkeypatch.setattr(
        "fedsim.engines.spyker.server.setup_telemetry_logger", lambda run_id: logger
    )
    return logger


def test_update_trace_records_alpha_and_rates(make_server, trace_logger, monkeypatch):
    monkeypatch.setenv("FEDSIM_UPDATE_TRACE", "on")
    server = make_server(run_id="r1")
    server.model_age = 3
    server._dispatched_lrs["c"] = 0.02
    update(server, 20.0, ref_age=0)
    (record,) = trace_logger.records
    assert record == {
        "log_type": "client_update",
        "run_id": "r1",
        "server_id": "A",
        "client_id": "c",
        "virtual_time": 0.0,
        "server_age": 3,
        "ref_age": 0,
        "staleness": 3,
        "alpha": pytest.approx(0.15),
        "lr_used": 0.02,
        "lr_next": server.client_learning_rates["c"],
        "update_count": 1,
    }


def test_update_trace_is_off_by_default(make_server, trace_logger, monkeypatch):
    monkeypatch.delenv("FEDSIM_UPDATE_TRACE", raising=False)
    server = make_server(run_id="r1")
    update(server, 20.0, ref_age=0)
    assert trace_logger.records == []


@pytest.mark.parametrize("sample_weighting,expected", [(False, 14.0), (True, 12.0)])
def test_only_opt_in_sample_weighting_clamps_the_blend(make_server, sample_weighting, expected):
    server = make_server(server_learning_rate=2.0, sample_weighting=sample_weighting)
    server.on_client_update(
        {"client_id": "c", "num_examples": 400, "metrics": {"ref_model_age": 0}}, [np.array([12.0])]
    )
    assert server.global_model_weights[0][0] == pytest.approx(expected)
