from __future__ import annotations

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
            ray.init(address="auto", ignore_reinit_error=True, include_dashboard=False)
        except Exception:
            ray.init(ignore_reinit_error=True, include_dashboard=False)
        _initialized = True
