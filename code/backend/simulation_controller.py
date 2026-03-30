from typing import Any, Callable
import importlib
import threading

import random
import numpy as np
import ray
import torch

from backend.services.hierfl_simulation_builder import build_hierfl_simulation, get_hierfl_evaluate_model
from backend.services.spyker_simulation_builder import build_spyker_simulation, get_spyker_evaluate_model

class SimulationController:
    _active_runs = 0
    _active_runs_lock = threading.Lock()

    def __init__(self, architecture: str, graph=None, training_config=None, simulation_settings=None, spyker_config=None):
        self.architecture = architecture
        self.graph = graph
        self.training_config = training_config
        self.simulation_settings = simulation_settings or {}
        self.spyker_config = spyker_config

    def start(self):
        graph_info = f" graph_id={self.graph.id}" if self.graph is not None else ""
        print(f"Starting architecture: {self.architecture}{graph_info}")

        if self.graph is None:
            raise ValueError(f"{self.architecture}_requires_graph")

        if self.architecture == "hierfl":
            return self._run_managed_simulation(
                builder=lambda: build_hierfl_simulation(
                    self.graph,
                    training_config=self.training_config,
                    run_time_limit=self.simulation_settings.get("run_time_limit"),
                    seed=self.simulation_settings.get("seed"),
                ),
                evaluator=get_hierfl_evaluate_model,
            )

        if self.architecture == "spyker":
            return self._run_managed_simulation(
                builder=lambda: build_spyker_simulation(
                    self.graph,
                    training_config=self.training_config,
                    spyker_config=self.spyker_config,
                    run_time_limit=self.simulation_settings.get("run_time_limit"),
                    idle_token_delay=self.simulation_settings.get("idle_token_delay"),
                    seed=self.simulation_settings.get("seed"),
                ),
                evaluator=get_spyker_evaluate_model,
            )

        raise NotImplementedError(f"Architecture not supported: {self.architecture}")

    def _run_managed_simulation(
        self,
        builder: Callable[[], Any],
        evaluator: Callable[[], Callable[[str], dict[str, float]]],
    ) -> dict[str, Any]:
        self._retain_runtime()
        try:
            return self._run_simulation(builder=builder, evaluator=evaluator)
        finally:
            self._release_runtime()

    def _run_simulation(
        self,
        builder: Callable[[], Any],
        evaluator: Callable[[], Callable[[str], dict[str, float]]],
    ) -> dict[str, Any]:
        seed = self.simulation_settings.get("seed")
        self._apply_seed(seed)
        simulation = builder()
        simulation.build()
        simulation.run()

        output_filename = self.simulation_settings.get("output_filename")
        evaluation = None
        if output_filename:
            simulation.save_model(output_filename)
            if self.simulation_settings.get("evaluate_model"):
                evaluate_model = evaluator()
                evaluation = evaluate_model(output_filename)
        result = {"output_filename": output_filename, "seed": seed}
        if evaluation is not None:
            result["evaluation"] = evaluation
        
        return result

    def _apply_seed(self, seed: int | None) -> None:
        if seed is None:
            return
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)

    @classmethod
    def _retain_runtime(cls) -> None:
        with cls._active_runs_lock:
            cls._active_runs += 1

    @classmethod
    def _release_runtime(cls) -> None:
        should_shutdown = False
        with cls._active_runs_lock:
            cls._active_runs = max(0, cls._active_runs - 1)
            should_shutdown = cls._active_runs == 0
        if should_shutdown:
            cls._shutdown_runtime()

    @staticmethod
    def _shutdown_runtime() -> None:
        try:
            ray_runtime = importlib.import_module("main.ray_runtime")
        except ModuleNotFoundError:
            if ray.is_initialized():
                ray.shutdown()
            return

        ray_runtime.shutdown_ray()
