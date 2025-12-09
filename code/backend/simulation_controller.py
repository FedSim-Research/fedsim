from framework.architectures.architecture_registry import get_architecture

class SimulationController:

    def __init__(self, config):
        self.config = config
        # self.arch = get_architecture(config.architecture)()
        self.arch = get_architecture(config.architecture)

    def start(self):
        print("Starting architecture:", self.config.architecture)
        # self.arch.start(self.config)