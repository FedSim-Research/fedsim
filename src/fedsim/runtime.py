from __future__ import annotations

import threading
from contextlib import contextmanager

import ray

_runtime_lock = threading.RLock()
_active_users = 0


def ensure_ray_initialized() -> None:
    with _runtime_lock:
        if ray.is_initialized():
            return
        try:
            ray.init(address="auto", ignore_reinit_error=True, include_dashboard=True)
        except Exception:
            ray.init(ignore_reinit_error=True, include_dashboard=True)


def shutdown_ray() -> None:
    with _runtime_lock:
        if _active_users:
            raise RuntimeError("fedsim_runtime_in_use: cannot shut down active managed runs")
        if ray.is_initialized():
            ray.shutdown()


@contextmanager
def managed_ray_runtime():
    """Protect lazy Ray use and release it after the last managed caller exits.

    Entry and final shutdown use the same lock, so a new caller cannot register
    between the zero-user check and shutdown. Nested callers share the runtime.
    """
    global _active_users
    with _runtime_lock:
        _active_users += 1
    try:
        yield
    finally:
        with _runtime_lock:
            _active_users -= 1
            if _active_users == 0:
                shutdown_ray()
