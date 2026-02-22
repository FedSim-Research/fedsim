from __future__ import annotations

import os
import threading
import ray

_init_lock = threading.Lock()
_initialized = False


def ensure_ray_initialized() -> None:
    global _initialized
    if _initialized or ray.is_initialized():
        _initialized = True
        return
    with _init_lock:
        if _initialized or ray.is_initialized():
            _initialized = True
            return
        try:
            configured_address = os.getenv("RAY_ADDRESS")
            if configured_address:
                ray.init(address=configured_address, ignore_reinit_error=True, include_dashboard=True)
            else:
                ray.init(address="auto", ignore_reinit_error=True, include_dashboard=True)
        except Exception:
            ray.init(ignore_reinit_error=True, include_dashboard=True)
        _initialized = True
