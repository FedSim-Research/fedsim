import logging
import random
from typing import Any, Callable

import numpy as np
import torch

from fedsim.runtime import managed_ray_runtime
from fedsim.services.hierfl_simulation_builder import (
    build_hierfl_simulation,
    get_hierfl_evaluate_model,
)
from fedsim.services.spyker_simulation_builder import (
    build_spyker_simulation,
    get_spyker_evaluate_model,
)
from fedsim.settings import checkpoint_path

logger = logging.getLogger(__name__)


class SimulationController:
    def __init__(
        self,
        architecture: str,
        graph=None,
        training_config=None,
        simulation_settings=None,
        spyker_config=None,
        run_id: str | None = None,
    ):
        self.architecture = architecture
        self.graph = graph
        self.training_config = training_config
        self.simulation_settings = simulation_settings or {}
        self.spyker_config = spyker_config
        self.run_id = run_id

    @managed_ray_runtime()
    def start(self):
        # Pre-download the dataset before simulation engines run in multiple Ray actors
        from fedsim.learning import preload_dataset

        dataset_id = self.simulation_settings.get("dataset")
        try:
            preload_dataset(dataset_id)
        except Exception as e:
            logger.error("Failed to preload dataset: %s", e)
            raise ValueError(f"Dataset {dataset_id} could not be pre-downloaded: {e}")

        graph_id = self.graph.id if self.graph is not None else None
        logger.info(
            "simulation_controller_start architecture=%s graph_id=%s seed=%s",
            self.architecture,
            graph_id,
            self.simulation_settings.get("seed"),
        )

        if self.graph is None:
            raise ValueError(f"{self.architecture}_requires_graph")

        if self.architecture == "hierfl":
            return self._run_simulation(
                builder=lambda: build_hierfl_simulation(
                    self.graph,
                    training_config=self.training_config,
                    run_time_limit=self.simulation_settings.get("run_time_limit"),
                    gpu_budget=self.simulation_settings.get("gpu_budget"),
                    dataset_id=self.simulation_settings.get("dataset"),
                    seed=self.simulation_settings.get("seed"),
                    run_id=self.run_id,
                    graph_id=graph_id,
                    eval_interval=self.simulation_settings.get("eval_interval"),
                ),
                evaluator=get_hierfl_evaluate_model,
            )

        if self.architecture == "spyker":
            return self._run_simulation(
                builder=lambda: build_spyker_simulation(
                    self.graph,
                    training_config=self.training_config,
                    spyker_config=self.spyker_config,
                    run_time_limit=self.simulation_settings.get("run_time_limit"),
                    idle_token_delay=self.simulation_settings.get("idle_token_delay"),
                    gpu_budget=self.simulation_settings.get("gpu_budget"),
                    dataset_id=self.simulation_settings.get("dataset"),
                    seed=self.simulation_settings.get("seed"),
                    run_id=self.run_id,
                    graph_id=graph_id,
                    eval_interval=self.simulation_settings.get("eval_interval"),
                ),
                evaluator=get_spyker_evaluate_model,
            )

        raise NotImplementedError(f"Architecture not supported: {self.architecture}")

    def _run_simulation(
        self,
        builder: Callable[[], Any],
        evaluator: Callable[[], Callable[[str], dict[str, float]]],
    ) -> dict[str, Any]:
        seed = self.simulation_settings.get("seed")
        self._apply_seed(seed)
        simulation = builder()
        logger.debug("simulation_build_start architecture=%s", self.architecture)
        simulation.build()
        logger.debug("simulation_run_start architecture=%s", self.architecture)
        simulation.run()
        logger.debug("simulation_run_finished architecture=%s", self.architecture)

        output_filename = self.simulation_settings.get("output_filename")
        evaluation = None
        if output_filename:
            output_filename = str(checkpoint_path(output_filename))
            simulation.save_model(output_filename)
            if self.simulation_settings.get("evaluate_model"):
                evaluate_model = evaluator()
                evaluation = evaluate_model(
                    output_filename, self.simulation_settings.get("dataset", "uoft-cs/cifar10")
                )
        result = {"output_filename": output_filename, "seed": seed}
        if evaluation is not None:
            result["evaluation"] = evaluation
        logger.info(
            "simulation_controller_finished architecture=%s output_filename=%s evaluated=%s",
            self.architecture,
            output_filename,
            evaluation is not None,
        )
        return result

    def _apply_seed(self, seed: int | None) -> None:
        if seed is None:
            logger.debug("simulation_seed_not_set architecture=%s", self.architecture)
            return
        random.seed(seed)
        np.random.seed(seed)
        torch.manual_seed(seed)
        logger.info("simulation_seed_applied architecture=%s seed=%s", self.architecture, seed)
