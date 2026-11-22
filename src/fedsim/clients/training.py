from collections import OrderedDict
from typing import List

import numpy as np
import torch
from torch.utils.data import DataLoader

from fedsim.learning import Net, load_data, test, train


class TrainingClient:
    def __init__(
        self,
        partition_id: int,
        num_partitions: int,
        dataset_id: str | None = None,
        seed: int | None = None,
        *,
        partition_seed: int | None = None,
        dataset_provider=None,
        model: Net | None = None,
    ):
        self.partition_id = partition_id
        self.num_partitions = num_partitions
        self.seed = seed
        self.partition_seed = partition_seed
        self.dataset_provider = dataset_provider
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        self.dataset_id = dataset_id
        # A serialized worker can reuse its model: every fit/evaluate loads all
        # incoming parameters, and fit creates a fresh optimizer on every call.
        self.net = (Net(seed=seed) if model is None else model).to(self.device)

    def _ensure_data_loaded(self):
        if not hasattr(self, "trainloader"):
            self.trainloader, self.testloader = load_data(
                self.partition_id,
                self.num_partitions,
                seed=self.seed,
                dataset_id=self.dataset_id,
                partition_seed=self.partition_seed,
                dataset_provider=self.dataset_provider,
            )

    def get_parameters(self) -> List[np.ndarray]:
        state_dict = self.net.state_dict()
        return [val.cpu().numpy() for _, val in state_dict.items()]

    def set_parameters(self, parameters: List[np.ndarray]):
        current = self.net.state_dict()
        if len(parameters) != len(current):
            raise ValueError("client_parameter_count_mismatch")
        state_dict = OrderedDict()
        for (name, target), value in zip(current.items(), parameters, strict=True):
            tensor = torch.tensor(value)
            if tensor.shape != target.shape:
                raise ValueError(f"client_parameter_shape_mismatch: {name}")
            state_dict[name] = tensor
        # Validate every shape before copying any values into the shared model.
        self.net.load_state_dict(state_dict, strict=True)

    def fit(self, parameters: List[np.ndarray], config: dict) -> dict:
        self._ensure_data_loaded()
        self.set_parameters(parameters)

        epochs = int(config.get("epochs", 1))
        lr = float(config.get("lr", 0.01))
        batch_size = int(config.get("batch_size", 32))
        if batch_size < 1:
            batch_size = 32

        trainloader = self.trainloader
        if trainloader.batch_size != batch_size:
            trainloader = DataLoader(
                trainloader.dataset,
                batch_size=batch_size,
                shuffle=True,
                generator=trainloader.generator,
            )

        loss = train(self.net, trainloader, epochs, lr, self.device)

        return {
            "parameters": self.get_parameters(),
            "num_examples": len(trainloader.dataset),
            "metrics": {"train_loss": loss},
        }

    def evaluate(self, parameters: List[np.ndarray], config: dict) -> dict:
        self._ensure_data_loaded()
        self.set_parameters(parameters)
        loss, accuracy = test(self.net, self.testloader, self.device)

        return {
            "loss": loss,
            "num_examples": len(self.testloader.dataset),
            "metrics": {"accuracy": accuracy, "loss": loss},
        }
