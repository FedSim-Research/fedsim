"""Share CPU admission across engines without resetting stateful clients."""

import asyncio
import logging
import math
import os
import threading

import ray

from fedsim.clients.handle import ClientHandle

CPU_POOL_NAME = "fedsim-cpu-execution-v1"
_pool_lock = threading.Lock()
_STARTUP_TIMEOUT = 30
_logger = logging.getLogger(__name__)


def cpu_worker_limit():
    value = os.environ.get("FEDSIM_CPU_WORKERS")
    if value is None:
        return None
    try:
        limit = int(value)
    except ValueError:
        raise ValueError("fedsim_invalid_cpu_worker_limit") from None
    if limit < 1:
        raise ValueError("fedsim_invalid_cpu_worker_limit")
    return limit


@ray.remote(num_cpus=1, num_gpus=0)
class CpuExecutionWorker:
    """Execute persistent logical clients within one CPU-reserving process."""

    def __init__(self):
        self._clients = {}
        self._contexts = {}
        self._model = None

    def ready(self):
        return True

    def call(self, actor, method, args, kwargs):
        if isinstance(actor, ClientHandle):
            from fedsim.clients.actor import VirtualClient

            if method != "handle_event":
                raise ValueError("Unsupported logical client method")
            key = (actor.execution_id, actor.client_id)
            if key not in self._clients:
                if actor.execution_id not in self._contexts:
                    context = ray.get(actor.context_ref)
                    if context.execution_id != actor.execution_id:
                        raise ValueError("Client execution identity does not match its context")
                    self._contexts[actor.execution_id] = context
                client = VirtualClient(
                    actor.client_id,
                    actor.client_config,
                    self._contexts[actor.execution_id],
                    model=self._model,
                )
                self._model = client.inner_client.net
                self._clients[key] = client
            kwargs = dict(kwargs)
            if isinstance(kwargs.get("direct_refs"), ray.ObjectRef):
                kwargs["direct_refs"] = ray.get(kwargs["direct_refs"])
            return self._clients[key].handle_event(*args, **kwargs)
        return ray.get(getattr(actor, method).remote(*args, **kwargs))

    def release_clients(self, execution_id):
        self._clients = {
            key: client for key, client in self._clients.items() if key[0] != execution_id
        }
        self._contexts.pop(execution_id, None)


@ray.remote(num_cpus=0, num_gpus=0)
class CpuExecutionPool:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("CPU execution capacity must be positive")
        self._workers = [CpuExecutionWorker.remote() for _ in range(capacity)]
        self._available = asyncio.Queue()
        for index in range(capacity):
            self._available.put_nowait(index)
        self._worker_locks = [asyncio.Lock() for _ in range(capacity)]
        self._closed_executions = set()
        self._ready = False
        self._startup_lock = asyncio.Lock()

    async def ready(self):
        async with self._startup_lock:
            if not self._ready:
                await asyncio.gather(*(worker.ready.remote() for worker in self._workers))
                self._ready = True
        return len(self._workers)

    async def call(self, actor, method, args, kwargs):
        if isinstance(actor, ClientHandle):
            # Fixed ownership preserves loader-generator and timing stream state.
            index = actor.client_config["dataset_partition_id"] % len(self._workers)
            async with self._worker_locks[index]:
                if actor.execution_id in self._closed_executions:
                    raise RuntimeError("Client execution has already been released")
                return await self._workers[index].call.remote(actor, method, args, kwargs)
        index = await self._available.get()
        try:
            async with self._worker_locks[index]:
                return await self._workers[index].call.remote(actor, method, args, kwargs)
        finally:
            self._available.put_nowait(index)

    async def release_clients(self, execution_id):
        """Drain active callbacks and reject queued/future work for a finished run."""
        self._closed_executions.add(execution_id)

        async def release(index):
            async with self._worker_locks[index]:
                await self._workers[index].release_clients.remote(execution_id)

        await asyncio.gather(*(release(index) for index in range(len(self._workers))))

    def close(self):
        for worker in self._workers:
            ray.kill(worker, no_restart=True)


def get_cpu_execution_pool():
    """Get one pool per Ray namespace, shared by concurrent engine controllers."""
    limit = cpu_worker_limit()
    with _pool_lock:
        try:
            pool = ray.get_actor(CPU_POOL_NAME)
        except ValueError:
            capacity = math.floor(ray.available_resources().get("CPU", 0))
            if limit is not None:
                capacity = min(capacity, limit)
            if capacity < 1:
                raise ValueError(
                    "fedsim_requires_available_cpu: at least one free logical CPU is required"
                ) from None
            pool = CpuExecutionPool.options(name=CPU_POOL_NAME, get_if_exists=True).remote(capacity)
        try:
            capacity = ray.get(pool.ready.remote(), timeout=_STARTUP_TIMEOUT)
        except ray.exceptions.GetTimeoutError as exc:
            # A readiness timeout is fatal for the shared pool, not just this caller.
            # Other controllers holding or awaiting the same pool will fail as well.
            try:
                ray.get(pool.close.remote(), timeout=5)
            except ray.exceptions.RayError:
                _logger.exception("Could not close CPU workers after startup timeout")
            try:
                ray.kill(pool, no_restart=True)
            except ray.exceptions.RayError:
                _logger.exception("Could not terminate CPU pool after startup timeout")
            raise RuntimeError(
                "fedsim_cpu_workers_unavailable: CPU workers could not start within "
                f"{_STARTUP_TIMEOUT} seconds; check the cluster's free CPU capacity"
            ) from exc
        if limit is not None and capacity > limit:
            raise ValueError("fedsim_existing_cpu_pool_exceeds_worker_limit")
        return pool
