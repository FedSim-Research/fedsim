from __future__ import annotations

import os
import threading
import ray

_init_lock = threading.Lock()


def _init_ray() -> None:
    # Use explicit cluster address only when configured.
    # This avoids long hangs with stale auto-discovery state.
    address = os.environ.get("RAY_ADDRESS")
    if address:
        try:
            ray.init(address=address, ignore_reinit_error=True, include_dashboard=False)
            return
        except Exception:
            pass
    ray.init(ignore_reinit_error=True, include_dashboard=False)


def ensure_ray_initialized() -> None:
    if ray.is_initialized():
        return
    with _init_lock:
        if ray.is_initialized():
            return
        _init_ray()
