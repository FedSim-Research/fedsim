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

## NVIDIA GPUs

With Docker configured for NVIDIA GPU access:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose -f compose.yaml -f compose.gpu.yaml down
```

The overlay selects the CUDA image for both Python services. GPU resource budgets
are selected per run. Current training clients run on CPU; evaluation can use a GPU.
