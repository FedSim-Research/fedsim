from pathlib import Path
import json
from pydantic import BaseModel
from typing import List, Dict

class ServerConfig(BaseModel):
    id: int
    region: str
    cpus: int
    gpus: int

class ClientGroupConfig(BaseModel):
    type: str
    count: int
    region: str

class DatasetConfig(BaseModel):
    name: str
    path: str
    split_strategy: str
    mean_datapoints_per_user: int

class ModelConfig(BaseModel):
    name: str

class NetworkConfig(BaseModel):
    latency_matrix: Dict[str, Dict[str, int]]
    packetloss: float
    jitter: int

class SimulationSettings(BaseModel):
    rounds: int
    seed: int
    evaluate_every: int
    parallel_runs: int
    local_epochs: int
    local_learning_rate: float
    central_learning_rate: float
    batch_size: int

class SimulationConfig(BaseModel):
    architecture: str
    dataset: DatasetConfig
    model: ModelConfig
    servers: List[ServerConfig]
    clients: List[ClientGroupConfig]
    network: NetworkConfig
    simulation: SimulationSettings

CURRENT_DIR = Path(__file__).resolve().parent
DEFAULT_CONFIG_PATH = CURRENT_DIR / "default_config.json"

def load_config(path: str | Path = DEFAULT_CONFIG_PATH):
    """
        Load the simulation config from JSON and return a `SimulationConfig` object.
    """
    path = Path(path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(path, "r") as f:
        data = json.load(f)

    return SimulationConfig(**data)
