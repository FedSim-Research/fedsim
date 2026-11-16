from dataclasses import dataclass, field
from typing import Literal


@dataclass
class SpykerAlgorithmConfig:
    """Parameters specific to the Spyker algorithms."""

    # --- Algorithm 1: Client Learning Rate Decay ---
    decay_beta: float = 0.05
    decay_mode: Literal["absolute", "relative"] = "absolute"
    min_learning_rate: float = 1e-6

    # --- Algorithm 2: Server Synchronization Triggers ---
    # "auto" resolves to n_C / (5n) per Zuo et al. 2024 (Table 2).
    h_inter: int | Literal["auto"] = 5
    h_intra: int = 350

    # --- Server Aggregation ---
    sigmoid_phi: float = 1.5
    server_learning_rate: float = 0.6
    staleness_mode: Literal["reciprocal", "none", "delta"] = "reciprocal"

    # Reserved compatibility field; neither engine simulates TCP retransmissions.
    tcp_rto_delay: float = 0.2


@dataclass
class TrainingConfig:
    """Hyperparameters for the local model training on clients."""

    local_epochs: int = 1
    learning_rate: float = 0.01
    batch_size: int = 32
    # Used to calculate virtual training duration
    model_complexity: float = 1.0


@dataclass
class SimulationConfig:
    """Global physics and limits for the simulation engine."""

    # When to stop the simulation (Virtual Seconds)
    run_time_limit: float = 5000.0

    # Cadence for model evaluation during training, 0.0 means disabled logging.
    eval_time_delay: float = 0.0

    # The 'Heartbeat' delay during token idle state (Virtual Seconds)
    idle_token_delay: float = 1.0


@dataclass
class FullConfiguration:
    spyker: SpykerAlgorithmConfig = field(default_factory=SpykerAlgorithmConfig)
    training: TrainingConfig = field(default_factory=TrainingConfig)
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
