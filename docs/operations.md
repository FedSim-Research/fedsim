# Operations

Run Compose commands from the repository root:

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f backend
docker compose down
```

| Interface | Address |
| --- | --- |
| FedSim | [localhost:8088](http://localhost:8088) |
| API documentation | [localhost:8088/api/docs](http://localhost:8088/api/docs) |
| Grafana | [localhost:8088/grafana/](http://localhost:8088/grafana/) |
| Ray | [localhost:8088/ray/](http://localhost:8088/ray/) |
| Prometheus | [localhost:8088/prometheus/](http://localhost:8088/prometheus/) |

The HTTP listener binds to localhost. Grafana allows anonymous access to support
embedded dashboards. This configuration is intended for a local research
workstation; configure authentication before exposing it to other machines.

Set `DEPLOY_HTTP_PORT=8090` in a root `.env` file to change the HTTP port.
Compose sets Uvicorn's `UVICORN_ROOT_PATH=/api` for the reverse-proxy prefix.
Native deployments behind a subpath should set this server option too.

## Runtime state

Compose mounts `var/` at `/var/lib/fedsim` in the Python services:

| Directory | Contents |
| --- | --- |
| `var/database/` | SQLite database |
| `var/cache/` | Download and partition caches |
| `var/datasets/` | Evaluation datasets |
| `var/models/` | Checkpoints with relative output filenames |
| `var/logs/` | Per-run JSONL evaluation telemetry |
| `var/exports/` | CSV run exports |

`docker compose down` preserves these files. To back up the SQLite database,
stop the stack before copying `var/`. Ray's own temporary logs use a named volume.

Native Python processes use `./var` relative to their working directory by
default. Set `FEDSIM_DATA_DIR` to an absolute path to choose another location.
`FEDSIM_TELEMETRY_LOG_DIR` and `HF_DATASETS_CACHE` can override the corresponding
subdirectories. With an external Ray cluster, use shared storage and consistent
paths on every node. Dataset files and checkpoints are not distributed by the API.

## CPU capacity

Simulation startup requires at least one free logical Ray CPU. Both engines
share a pool sized to the whole CPUs available at its creation; for example,
2.5 free CPUs allow two concurrent training or periodic evaluation callbacks.
Coordination actors do not reserve these CPUs. A reused pool keeps its original
capacity and CPU reservations for its lifetime. Shutting down its owning Ray
job releases the pool. Standalone Python callers should call `ray.shutdown()`
when finished.

If fewer than one CPU is free, startup fails with
`fedsim_requires_available_cpu`. If competing allocations prevent workers from
starting within 30 seconds, startup fails with `fedsim_cpu_workers_unavailable`.
This timeout tears down the shared pool, so other controllers using that pool
also fail; it is not an isolated timeout for one engine.
Check the Ray cluster's resource allocations before retrying. Logical CPU
reservations are scheduling limits; they do not impose memory or process
quotas. Large client populations can still exhaust workstation RAM.

## NVIDIA GPUs

The GPU image uses PyTorch 2.15 with CUDA 13.2. It requires a compatible NVIDIA
driver; a working older CUDA installation is not sufficient. The bundled CPU
image is the default for workstations that do not meet that requirement.

With Docker configured for compatible NVIDIA GPU access:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose -f compose.yaml -f compose.gpu.yaml down
```

The overlay selects the CUDA image for both Python services. GPU resource budgets
are selected per run. Current training clients run on CPU; evaluation can use a GPU.

## Dependency updates

Container images are pinned by version and digest. Python environments are
installed from `uv.lock`; the frontend uses `package-lock.json` and its declared
npm version. Update pins and lockfiles together, rebuild, and rerun integration
checks before adopting a new stack.
