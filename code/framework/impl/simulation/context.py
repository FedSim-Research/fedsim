from contextvars import ContextVar
from typing import Dict, Any
import ray
from specs.client_spec import ClientSpec
from specs.server_spec import ServerSpec


class SimulationContext:
    """
    A container for the static 'physics' of the simulation.
    This object is meant to be passed to Ray workers or accessed via a Singleton.
    """

    def __init__(
        self,
        orchestrator_actor: ray.ObjectRef | Any,
        client_registry: Dict[str, ClientSpec],
        server_registry: Dict[str, ServerSpec],
    ):
        self.orchestrator = orchestrator_actor
        self.client_registry = client_registry
        self.server_registry = server_registry
        
        self.server_actor_handles = None

    def get_client_spec(self, client_id: str) -> ClientSpec:
        if client_id not in self.client_registry:
            raise KeyError(f"Client ID '{client_id}' not found in registry.")
        return self.client_registry[client_id]

    def get_server_spec(self, server_id: str) -> ServerSpec:
        if server_id not in self.server_registry:
            raise KeyError(f"Server ID '{server_id}' not found in registry.")
        return self.server_registry[server_id]
    
    def set_server_actor_handles(self, handles: Dict[str, Any]):
        self.server_actor_handles = handles


# Context-local singleton to avoid cross-request overwrites in concurrent runs.
_global_context: ContextVar[SimulationContext | None] = ContextVar(
    "simulation_global_context",
    default=None,
)


def set_global_context(ctx: SimulationContext):
    _global_context.set(ctx)


def get_global_context() -> SimulationContext:
    ctx = _global_context.get()
    if ctx is None:
        raise RuntimeError("Global SimulationContext has not been set.")
    return ctx
