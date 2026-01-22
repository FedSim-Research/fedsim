from backend.services.hierfl_simulation_builder import build_hierfl_simulation, get_hierfl_evaluate_model

class SimulationController:

    def __init__(self, architecture: str, graph=None, training_config=None, simulation_settings=None):
        self.architecture = architecture
        self.graph = graph
        self.training_config = training_config
        self.simulation_settings = simulation_settings or {}

    def start(self):
        graph_info = f" graph_id={self.graph.id}" if self.graph is not None else ""
        print(f"Starting architecture: {self.architecture}{graph_info}")

        if self.architecture == "hierfl":
            if self.graph is None:
                raise ValueError("hierfl_requires_graph")
            run_time_limit = self.simulation_settings.get("run_time_limit")
            simulation = build_hierfl_simulation(
                self.graph,
                training_config=self.training_config,
                run_time_limit=run_time_limit,
            )
            simulation.build()
            simulation.run()
            output_filename = self.simulation_settings.get("output_filename")
            if output_filename:
                simulation.save_model(output_filename)
                if self.simulation_settings.get("evaluate_model"):
                    evaluate_model = get_hierfl_evaluate_model()
                    evaluate_model(output_filename)
            return

        raise NotImplementedError(f"Architecture not supported: {self.architecture}")
