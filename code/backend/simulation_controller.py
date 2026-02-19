from typing import Any, Callable

from backend.services.hierfl_simulation_builder import build_hierfl_simulation, get_hierfl_evaluate_model
from backend.services.spyker_simulation_builder import build_spyker_simulation, get_spyker_evaluate_model

class SimulationController:

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
            return self._run_simulation(
                builder=lambda: build_hierfl_simulation(
                    self.graph,
                    training_config=self.training_config,
                    run_time_limit=self.simulation_settings.get("run_time_limit"),
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
                ),
                evaluator=get_spyker_evaluate_model,
            )

        raise NotImplementedError(f"Architecture not supported: {self.architecture}")

    def _run_simulation(
        self,
        builder: Callable[[], Any],
        evaluator: Callable[[], Callable[[str], dict[str, float]]],
    ) -> dict[str, Any]:
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
        result = {"output_filename": output_filename}
        if evaluation is not None:
            result["evaluation"] = evaluation
        return result
