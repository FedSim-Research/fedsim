from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fedsim import learning, runtime
from fedsim.services import controller
from fedsim.settings import data_dir


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
def test_controller_routes_runs_and_checkpoints_through_installed_package(
    monkeypatch, architecture
):
    preload = Mock()
    simulation = Mock()
    builder = Mock(return_value=simulation)
    shutdown = Mock()
    evaluator = Mock(return_value={"accuracy": 0.5, "avg_loss": 0.8})
    monkeypatch.setattr(learning, "preload_dataset", preload)
    monkeypatch.setattr(controller, f"build_{architecture}_simulation", builder)
    monkeypatch.setattr(controller, f"get_{architecture}_evaluate_model", lambda: evaluator)
    monkeypatch.setattr(runtime, "shutdown_ray", shutdown)

    result = controller.SimulationController(
        architecture,
        graph=SimpleNamespace(id=123),
        training_config={"epochs": 1, "lr": 0.01},
        simulation_settings={
            "dataset": "uoft-cs/cifar10",
            "output_filename": "synthetic.pth",
            "evaluate_model": True,
            "seed": 42,
        },
        run_id="test-run",
    ).start()

    preload.assert_called_once_with("uoft-cs/cifar10")
    assert builder.call_args.kwargs["run_id"] == "test-run"
    simulation.build.assert_called_once()
    simulation.run.assert_called_once()
    expected = data_dir() / "models/synthetic.pth"
    simulation.save_model.assert_called_once_with(str(expected))
    evaluator.assert_called_once_with(str(expected), "uoft-cs/cifar10")
    assert Path(result["output_filename"]) == expected
    assert result["evaluation"]["accuracy"] == 0.5
    shutdown.assert_called_once()
    assert runtime._active_users == 0


@pytest.mark.parametrize("architecture", ["hierfl", "spyker"])
@pytest.mark.parametrize("failure", ["preload", "build", "run", "save", "evaluate"])
def test_controller_releases_runtime_after_each_failure(monkeypatch, architecture, failure):
    preload = Mock()
    simulation = Mock()
    evaluator = Mock()
    actions = {
        "preload": preload,
        "build": simulation.build,
        "run": simulation.run,
        "save": simulation.save_model,
        "evaluate": evaluator,
    }
    actions[failure].side_effect = RuntimeError("deliberate failure")
    shutdown = Mock()
    monkeypatch.setattr(learning, "preload_dataset", preload)
    monkeypatch.setattr(
        controller, f"build_{architecture}_simulation", Mock(return_value=simulation)
    )
    monkeypatch.setattr(controller, f"get_{architecture}_evaluate_model", lambda: evaluator)
    monkeypatch.setattr(runtime, "shutdown_ray", shutdown)
    instance = controller.SimulationController(
        architecture,
        graph=SimpleNamespace(id=123),
        simulation_settings={"output_filename": "failure.pth", "evaluate_model": True},
    )
    with pytest.raises((ValueError, RuntimeError), match="deliberate failure"):
        instance.start()
    shutdown.assert_called_once()
    assert runtime._active_users == 0


@pytest.mark.parametrize("preload_fails", [False, True])
def test_finishing_controller_does_not_interrupt_another_preload(monkeypatch, preload_fails):
    preloading = Event()
    resume = Event()
    shutdown = Mock()

    def preload(dataset):
        if dataset == "slow":
            preloading.set()
            assert resume.wait(5)
            if preload_fails:
                raise RuntimeError("slow preload failed")

    monkeypatch.setattr(learning, "preload_dataset", preload)
    monkeypatch.setattr(runtime, "shutdown_ray", shutdown)
    monkeypatch.setattr(
        controller.SimulationController, "_run_simulation", lambda self, **kwargs: {"done": True}
    )
    slow = controller.SimulationController(
        "spyker", graph=SimpleNamespace(id=1), simulation_settings={"dataset": "slow"}
    )
    fast = controller.SimulationController("hierfl", graph=SimpleNamespace(id=2))
    with ThreadPoolExecutor(max_workers=1) as threads:
        pending = threads.submit(slow.start)
        try:
            assert preloading.wait(5)
            assert fast.start() == {"done": True}
            shutdown.assert_not_called()
        finally:
            resume.set()
        if preload_fails:
            with pytest.raises(ValueError, match="slow preload failed"):
                pending.result(timeout=5)
        else:
            assert pending.result(timeout=5) == {"done": True}
    shutdown.assert_called_once()
    assert runtime._active_users == 0
