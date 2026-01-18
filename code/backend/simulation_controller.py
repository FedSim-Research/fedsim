from backend.services.hierfl_simulation_builder import build_hierfl_simulation

class SimulationController:

    def __init__(self, architecture: str, graph=None, training_config=None):
        self.architecture = architecture
        self.graph = graph
        self.training_config = training_config

    def start(self):
        graph_info = f" graph_id={self.graph.id}" if self.graph is not None else ""
        print(f"Starting architecture: {self.architecture}{graph_info}")

        if self.architecture == "hierfl":
            if self.graph is None:
                raise ValueError("hierfl_requires_graph")
            simulation = build_hierfl_simulation(self.graph, training_config=self.training_config)
            simulation.build()
            simulation.run()
            return

        raise NotImplementedError(f"Architecture not supported: {self.architecture}")