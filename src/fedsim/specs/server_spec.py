from dataclasses import dataclass

from fedsim.specs.network_metrics import Network
from fedsim.specs.performance_metrics import Performance


@dataclass
class ServerSpec:
    id: str
    name: str
    performance_metrics: Performance
    network_metrics: (
        dict[str, Network] | None
    )  # maps target ID's to network properties (edges in graph), None for Super Server. See [1] for more info.
    upload_speed: float  # in Mbps
    download_speed: float  # in Mbps


# [1] Hierarchical:
#       The dictionary for network metrics is only necessary for Edge Servers.
#       A Client or a Super Server will only ever directly communicate with an Edge Server.
#       Therefore, if they want to send a message, they simply retrieve the ServerSpec of
#       the particular Edge Server they are trying to communicate with from the global context.
#       Using their own ID as the key for the network metrics dict, they can get the info for their
#       particular "edge" in the graph of the simulation.

#       E.g. SuperServer <---(network metrics)---> EdgeServer, where (network metrics) includes
#       - latency_avg
#       - latency_stddev
#       - packet_loss_avg
#       - packet_loss_stddev
#       of this particular connection.
