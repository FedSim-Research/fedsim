from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from fedsim import learning
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
    monkeypatch.setattr(controller, "shutdown_ray", shutdown)

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
    assert controller.SimulationController._active_runs == 0
