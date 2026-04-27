import torch
import flwr
import random
import numpy as np
from typing import Dict
from collections import OrderedDict
from torch.utils.data import DataLoader
from flwr.common import (
    FitIns,
    FitRes,
    EvaluateIns,
    EvaluateRes,
    Parameters,
    Status,
    Code,
    Scalar,
    ndarrays_to_parameters,
    parameters_to_ndarrays,
)

from main.task import Net, load_data, train, test


class SimulationFlowerClient(flwr.client.Client):
    def __init__(
        self,
        partition_id: int,
        num_partitions: int,
        dataset_id: str | None = None,
        seed: int | None = None,
    ):
        self.partition_id = partition_id
        self.num_partitions = num_partitions
        self.seed = seed
        self.device = torch.device("cuda:0" if torch.cuda.is_available() else "cpu")
        if seed is not None:
            random.seed(seed)
            np.random.seed(seed)
            torch.manual_seed(seed)

        self.dataset_id = dataset_id

        # 1. Initialize Model
        self.net = Net().to(self.device)

    def _ensure_data_loaded(self):
        if not hasattr(self, "trainloader"):
            # 2. Load Data (Using the FederatedDataset logic from task.py)
            # This will download/cache dataset partitions on the first run.
            self.trainloader, self.testloader = load_data(
                self.partition_id,
                self.num_partitions,
                seed=self.seed,
                dataset_id=self.dataset_id,
            )

    def get_parameters(self, config: Dict[str, Scalar]) -> Parameters:
        # Convert PyTorch parameters to Flower Parameters
        state_dict = self.net.state_dict()
        # Keep keys ordered to ensure weight alignment
        ndarrays = [val.cpu().numpy() for _, val in state_dict.items()]
        return ndarrays_to_parameters(ndarrays)

    def set_parameters(self, parameters: Parameters):
        # Convert Flower Parameters back to PyTorch
        ndarrays = parameters_to_ndarrays(parameters)
        params_dict = zip(self.net.state_dict().keys(), ndarrays)
        state_dict = OrderedDict({k: torch.tensor(v) for k, v in params_dict})
        self.net.load_state_dict(state_dict, strict=True)

    def fit(self, ins: FitIns) -> FitRes:
        self._ensure_data_loaded()
        
        # 1. Update Local Model with Global Weights
        self.set_parameters(ins.parameters)

        # 2. Extract Config (Passed from SuperServer -> EdgeServer -> Client)
        epochs = int(ins.config.get("epochs", 1))
        lr = float(ins.config.get("lr", 0.001))
        batch_size = int(ins.config.get("batch_size", 32))
        if batch_size < 1:
            batch_size = 32

        trainloader = self.trainloader
        if trainloader.batch_size != batch_size:
            trainloader = DataLoader(
                trainloader.dataset,
                batch_size=batch_size,
                shuffle=True,
            )

        # 3. Train (using task.py logic)
        loss = train(self.net, trainloader, epochs, lr, self.device)

        # 4. Return Results
        # Note: We return the updated weights and the 'real' training loss
        return FitRes(
            status=Status(code=Code.OK, message="Success"),
            parameters=self.get_parameters(config={}),
            num_examples=len(trainloader.dataset),
            metrics={"train_loss": loss},
        )

    def evaluate(self, ins: EvaluateIns) -> EvaluateRes:
        self._ensure_data_loaded()
        
        # 1. Update Local Model
        self.set_parameters(ins.parameters)

        # 2. Test (using task.py logic)
        loss, accuracy = test(self.net, self.testloader, self.device)

        # 3. Return Results
        return EvaluateRes(
            status=Status(code=Code.OK, message="Success"),
            loss=loss,
            num_examples=len(self.testloader.dataset),
            metrics={"accuracy": accuracy, "loss": loss},
        )
