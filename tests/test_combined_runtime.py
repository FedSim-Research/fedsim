from concurrent.futures import ThreadPoolExecutor
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fedsim import runtime
from fedsim.services import simulation_run_queue as module


@pytest.mark.parametrize("failure", [None, "hierfl", "spyker"])
def test_combined_pair_waits_for_both_engines_before_shutdown(monkeypatch, failure):
    queue = module.SimulationRunQueue()
    slow_architecture = "hierfl" if failure == "spyker" else "spyker"
    slow_started = Event()
    fast_finished = Event()
    resume = Event()
    shutdown = Mock()
    monkeypatch.setattr(runtime, "shutdown_ray", shutdown)
    monkeypatch.setattr(
        module.graph_service,
        "get_graph",
        lambda graph_id: SimpleNamespace(architecture="hierfl" if graph_id == 1 else "spyker"),
    )

    def gpu_capacity():
        assert runtime._active_users > 0
        return 1.0

    capacity = Mock(side_effect=gpu_capacity)
    monkeypatch.setattr(module, "_get_cluster_gpu_capacity", capacity)

    def run(architecture, **kwargs):
        # Model a controller delayed before registration/preload.
        if architecture == slow_architecture:
            slow_started.set()
            assert resume.wait(5)
        with runtime.managed_ray_runtime():
            if architecture != slow_architecture:
                fast_finished.set()
            if architecture == failure:
                raise ValueError("engine failed")
            assert kwargs["simulation_settings"]["gpu_budget"] == 0.5
            return {"seed": kwargs["seed"], "output_filename": None}

    monkeypatch.setattr(queue, "_run_architecture_once", run)
    job = queue.enqueue_combined(
        {
            arch: {"graph_id": graph_id, "simulation_settings": {"seed_set": [42], "gpu_budget": 1}}
            for arch, graph_id in [("hierfl", 1), ("spyker", 2)]
        }
    )
    with ThreadPoolExecutor(max_workers=1) as threads:
        result = threads.submit(queue._run_combined_job, job)
        try:
            assert slow_started.wait(5)
            assert fast_finished.wait(5)
            assert not result.done()
            shutdown.assert_not_called()
        finally:
            resume.set()
        if failure:
            with pytest.raises(ValueError, match="engine failed"):
                result.result(timeout=5)
        else:
            assert result.result(timeout=5)["completed_repetitions"] == 1
    shutdown.assert_called_once()
    capacity.assert_called_once()
    assert runtime._active_users == 0


def test_combined_repetitions_release_runtime_between_seed_pairs(monkeypatch):
    queue = module.SimulationRunQueue()
    shutdown = Mock()
    monkeypatch.setattr(runtime, "shutdown_ray", shutdown)
    monkeypatch.setattr(
        module.graph_service,
        "get_graph",
        lambda graph_id: SimpleNamespace(architecture="hierfl" if graph_id == 1 else "spyker"),
    )

    def run(seed, repetition_index, **kwargs):
        assert runtime._active_users > 0
        assert shutdown.call_count == repetition_index - 1
        return {"seed": seed, "output_filename": None}

    monkeypatch.setattr(queue, "_run_architecture_once", run)
    job = queue.enqueue_combined(
        {
            arch: {"graph_id": graph_id, "simulation_settings": {"seed_set": [42, 17]}}
            for arch, graph_id in [("hierfl", 1), ("spyker", 2)]
        }
    )
    result = queue._run_combined_job(job)
    assert result["completed_repetitions"] == 2
    assert shutdown.call_count == 2
    assert runtime._active_users == 0
