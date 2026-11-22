import asyncio
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
import ray

from fedsim.engines.hierarchical.coordinator import SuperServer
from fedsim.engines.hierarchical.edge import EdgeServer
from fedsim.engines.spyker.server import SpykerServer
from fedsim.learning import DatasetProvider
from fedsim.simulation.orchestrator import SimulationOrchestrator
from fedsim.telemetry.evaluator import PeriodicEvaluator


@pytest.fixture(autouse=True)
def default_worker_limit(monkeypatch):
    monkeypatch.delenv("FEDSIM_CPU_WORKERS", raising=False)


@pytest.mark.parametrize("value", ["0", "-1", "1.5", "", "true"])
def test_invalid_cpu_worker_limit_is_rejected_before_ray_calls(monkeypatch, value):
    from fedsim.simulation import cpu_execution

    monkeypatch.setenv("FEDSIM_CPU_WORKERS", value)
    lookup = Mock()
    monkeypatch.setattr(ray, "get_actor", lookup)
    with pytest.raises(ValueError, match="invalid_cpu_worker_limit"):
        cpu_execution.get_cpu_execution_pool()
    lookup.assert_not_called()


def test_cpu_worker_limit_caps_available_slots_without_resizing_an_existing_pool(monkeypatch):
    from fedsim.simulation import cpu_execution

    monkeypatch.setenv("FEDSIM_CPU_WORKERS", "4")
    pool = SimpleNamespace(ready=SimpleNamespace(remote=lambda: "ready"))
    monkeypatch.setattr(ray, "get_actor", Mock(side_effect=ValueError("missing")))
    monkeypatch.setattr(ray, "available_resources", lambda: {"CPU": 16})
    monkeypatch.setattr(ray, "get", Mock(return_value=4))
    factory = Mock(return_value=SimpleNamespace(remote=Mock(return_value=pool)))
    monkeypatch.setattr(cpu_execution.CpuExecutionPool, "options", factory)
    assert cpu_execution.get_cpu_execution_pool() is pool
    factory.return_value.remote.assert_called_once_with(4)
    monkeypatch.setattr(ray, "get_actor", Mock(return_value=pool))
    monkeypatch.setattr(ray, "get", Mock(return_value=16))
    kill = Mock()
    monkeypatch.setattr(ray, "kill", kill)
    with pytest.raises(ValueError, match="existing_cpu_pool_exceeds"):
        cpu_execution.get_cpu_execution_pool()
    kill.assert_not_called()


# These resource assertions use metadata from the Ray version pinned in uv.lock.
@pytest.mark.parametrize(
    "actor",
    [
        SuperServer,
        EdgeServer,
        SpykerServer,
        DatasetProvider,
        SimulationOrchestrator,
        PeriodicEvaluator,
    ],
)
def test_idle_and_coordination_actors_do_not_reserve_cpu(actor):
    assert actor._default_options.get("num_cpus") == 0


@pytest.mark.parametrize("capacity", [1, 2, 4])
def test_shared_pool_bounds_calls_from_both_engines_and_initializes_once(monkeypatch, capacity):
    from fedsim.simulation import cpu_execution

    async def scenario():
        active = peak = ready_calls = 0

        async def ready():
            nonlocal ready_calls
            ready_calls += 1
            return True

        async def call(actor, method, args, kwargs):
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1
            return actor, args[0]

        worker = SimpleNamespace(
            ready=SimpleNamespace(remote=ready), call=SimpleNamespace(remote=call)
        )
        monkeypatch.setattr(cpu_execution.CpuExecutionWorker, "remote", lambda: worker)
        pool = cpu_execution.CpuExecutionPool.__ray_metadata__.modified_class(capacity)
        assert await pool.ready() == capacity
        assert await pool.ready() == capacity
        assert ready_calls == capacity
        requests = [("hierfl" if index % 2 else "spyker", index) for index in range(8)]
        results = await asyncio.gather(
            *[pool.call(actor, "handle_event", (index,), {}) for actor, index in requests]
        )
        assert results == requests
        assert peak == capacity

    asyncio.run(scenario())


def test_pool_returns_capacity_after_a_failed_call(monkeypatch):
    from fedsim.simulation import cpu_execution

    async def scenario():
        async def call(actor, method, args, kwargs):
            if args[0] == "fail":
                raise ValueError("training failed")
            return args[0]

        worker = SimpleNamespace(call=SimpleNamespace(remote=call))
        monkeypatch.setattr(cpu_execution.CpuExecutionWorker, "remote", lambda: worker)
        pool = cpu_execution.CpuExecutionPool.__ray_metadata__.modified_class(1)
        with pytest.raises(ValueError, match="training failed"):
            await pool.call("client", "handle_event", ("fail",), {})
        assert (
            await asyncio.wait_for(pool.call("client", "handle_event", ("next",), {}), timeout=1)
            == "next"
        )

    asyncio.run(scenario())


def test_cpu_worker_forwards_arguments_and_returns_actor_result(monkeypatch):
    from fedsim.simulation.cpu_execution import CpuExecutionWorker

    method = SimpleNamespace(remote=Mock(return_value="result-ref"))
    actor = SimpleNamespace(handle_event=method)
    get = Mock(return_value=["next-event"])
    monkeypatch.setattr(ray, "get", get)
    worker = CpuExecutionWorker.__ray_metadata__.modified_class()
    assert worker.call(actor, "handle_event", ("payload",), {"direct_refs": "weights"}) == [
        "next-event"
    ]
    method.remote.assert_called_once_with("payload", direct_refs="weights")
    get.assert_called_once_with("result-ref")
    assert CpuExecutionWorker._default_options["num_cpus"] == 1


@pytest.mark.parametrize("available", [0, 0.5])
def test_pool_rejects_insufficient_free_cpu_before_creating_workers(monkeypatch, available):
    from fedsim.simulation import cpu_execution

    monkeypatch.setattr(ray, "get_actor", Mock(side_effect=ValueError("missing")))
    monkeypatch.setattr(ray, "available_resources", lambda: {"CPU": available})
    factory = Mock()
    monkeypatch.setattr(cpu_execution.CpuExecutionPool, "options", factory)
    with pytest.raises(ValueError, match="fedsim_requires_available_cpu"):
        cpu_execution.get_cpu_execution_pool()
    factory.assert_not_called()


def test_pool_is_shared_and_uses_only_whole_available_cpu_slots(monkeypatch):
    from fedsim.simulation import cpu_execution

    pool = SimpleNamespace(ready=SimpleNamespace(remote=lambda: "ready"))
    monkeypatch.setattr(ray, "get_actor", Mock(side_effect=[ValueError("missing"), pool]))
    monkeypatch.setattr(ray, "available_resources", lambda: {"CPU": 2.75})
    monkeypatch.setattr(ray, "get", Mock(return_value=2))
    factory = Mock(return_value=SimpleNamespace(remote=Mock(return_value=pool)))
    monkeypatch.setattr(cpu_execution.CpuExecutionPool, "options", factory)
    assert cpu_execution.get_cpu_execution_pool() is pool
    assert cpu_execution.get_cpu_execution_pool() is pool
    factory.assert_called_once_with(name=cpu_execution.CPU_POOL_NAME, get_if_exists=True)
    factory.return_value.remote.assert_called_once_with(2)


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_pool_bootstrap_timeout_cleans_up_and_reports_capacity_problem(monkeypatch, cleanup_fails):
    from fedsim.simulation import cpu_execution

    pool = SimpleNamespace(
        ready=SimpleNamespace(remote=lambda: "ready"),
        close=SimpleNamespace(remote=lambda: "close"),
    )
    monkeypatch.setattr(ray, "get_actor", Mock(side_effect=ValueError("missing")))
    monkeypatch.setattr(ray, "available_resources", lambda: {"CPU": 1})
    cleanup_result = ray.exceptions.GetTimeoutError() if cleanup_fails else None
    monkeypatch.setattr(
        ray, "get", Mock(side_effect=[ray.exceptions.GetTimeoutError(), cleanup_result])
    )
    monkeypatch.setattr(
        cpu_execution.CpuExecutionPool,
        "options",
        Mock(return_value=SimpleNamespace(remote=Mock(return_value=pool))),
    )
    kill = Mock()
    monkeypatch.setattr(ray, "kill", kill)
    with pytest.raises(RuntimeError, match="fedsim_cpu_workers_unavailable"):
        cpu_execution.get_cpu_execution_pool()
    kill.assert_called_once_with(pool, no_restart=True)


@pytest.fixture
def orchestrator_class(monkeypatch):
    cls = SimulationOrchestrator.__ray_metadata__.modified_class
    monkeypatch.setattr(cls, "_log_worker", lambda self: None)
    return cls


@pytest.mark.parametrize("event_type", ["START_FIT", "EVALUATE"])
def test_orchestrator_routes_compute_events_through_cpu_pool(
    monkeypatch, orchestrator_class, event_type
):
    pool = SimpleNamespace(call=SimpleNamespace(remote=Mock(return_value="future")))
    target = SimpleNamespace(handle_event=SimpleNamespace(remote=Mock()))
    payload = {"event_type": event_type, "trigger_time": 0, "data": {}}
    monkeypatch.setattr(ray, "wait", lambda refs, **kwargs: (refs, []))
    monkeypatch.setattr(ray, "get", lambda ref: [])
    kernel = orchestrator_class(cpu_pool=pool)
    kernel.add_event(0, target, "handle_event", payload, "weights")
    kernel.run_until(0)
    pool.call.remote.assert_called_once_with(
        target, "handle_event", (payload,), {"direct_refs": "weights"}
    )
    target.handle_event.remote.assert_not_called()


def test_orchestrator_rejects_training_without_cpu_admission(orchestrator_class):
    target = SimpleNamespace(handle_event=SimpleNamespace(remote=Mock()))
    kernel = orchestrator_class()
    kernel.add_event(0, target, "handle_event", {"event_type": "START_FIT", "trigger_time": 0})
    with pytest.raises(RuntimeError, match="CPU execution pool"):
        kernel.run_until(0)
    target.handle_event.remote.assert_not_called()
