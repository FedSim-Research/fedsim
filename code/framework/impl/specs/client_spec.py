from dataclasses import dataclass
from specs.performance_metrics import Performance


@dataclass
class ClientSpec:
    id: str
    name: str
    performance_metrics: Performance
    upload_speed: float  # in Mbps
    download_speed: float  # in Mbps
