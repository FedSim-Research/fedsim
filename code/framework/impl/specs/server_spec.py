from dataclasses import dataclass
from specs.performance_metrics import Performance
from specs.network_metrics import Network


@dataclass
class ServerSpec:
    id: str
    name: str
    performance_metrics: Performance
    network_metrics: Network
