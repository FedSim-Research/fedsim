"""Share CPU admission across engines without resetting stateful clients."""

import asyncio
import logging
import math
import threading

import ray

CPU_POOL_NAME = "fedsim-cpu-execution-v1"
_pool_lock = threading.Lock()
_STARTUP_TIMEOUT = 30
_logger = logging.getLogger(__name__)


@ray.remote(num_cpus=1, num_gpus=0)
class CpuExecutionWorker:
    """Hold one logical CPU while a stateful compute actor handles a callback."""

    def ready(self):
        return True

    def call(self, actor, method, args, kwargs):
        return ray.get(getattr(actor, method).remote(*args, **kwargs))


@ray.remote(num_cpus=0, num_gpus=0)
class CpuExecutionPool:
    def __init__(self, capacity: int):
        if capacity < 1:
            raise ValueError("CPU execution capacity must be positive")
        self._workers = [CpuExecutionWorker.remote() for _ in range(capacity)]
        self._available = asyncio.Queue()
        for worker in self._workers:
            self._available.put_nowait(worker)
        self._ready = False
        self._startup_lock = asyncio.Lock()

    async def ready(self):
        async with self._startup_lock:
            if not self._ready:
                await asyncio.gather(*(worker.ready.remote() for worker in self._workers))
                self._ready = True
        return len(self._workers)

    async def call(self, actor, method, args, kwargs):
        worker = await self._available.get()
        try:
            return await worker.call.remote(actor, method, args, kwargs)
        finally:
            self._available.put_nowait(worker)

    def close(self):
        for worker in self._workers:
            ray.kill(worker, no_restart=True)


def get_cpu_execution_pool():
    """Get one pool per Ray namespace, shared by concurrent engine controllers."""
    with _pool_lock:
        try:
            pool = ray.get_actor(CPU_POOL_NAME)
        except ValueError:
            capacity = math.floor(ray.available_resources().get("CPU", 0))
            if capacity < 1:
                raise ValueError(
                    "fedsim_requires_available_cpu: at least one free logical CPU is required"
                ) from None
            pool = CpuExecutionPool.options(name=CPU_POOL_NAME, get_if_exists=True).remote(capacity)
        try:
            ray.get(pool.ready.remote(), timeout=_STARTUP_TIMEOUT)
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
        return pool
