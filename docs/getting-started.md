# Getting started

This guide shows how to start FedSim, run a first simulation and find the most
common commands. For a local development setup without Docker, see
[Development](development.md).

## Requirements

- Docker with Docker Compose v2
- Enough free RAM for the chosen client population; memory grows with the number of logical clients
- Internet access for the first build (dependencies and CIFAR-10 download)

An NVIDIA GPU is optional; see [GPU deployment](#gpu-deployment).

## Start FedSim

From the repository root:

```bash
git clone https://github.com/FedSim-Research/fedsim.git
cd fedsim
docker compose up -d --build
```

The first build takes several minutes. Check that all services are running:

```bash
docker compose ps
```

Then open **[localhost:8088](http://localhost:8088)**.

| Interface | Address |
| --- | --- |
| FedSim (editor and dashboard) | [localhost:8088](http://localhost:8088) |
| API documentation | [localhost:8088/api/docs](http://localhost:8088/api/docs) |
| Grafana | [localhost:8088/grafana/](http://localhost:8088/grafana/) |
| Ray dashboard | [localhost:8088/ray/](http://localhost:8088/ray/) |
| Prometheus | [localhost:8088/prometheus/](http://localhost:8088/prometheus/) |

All interfaces bind to localhost only. To use a different port, create a `.env`
file in the repository root with `DEPLOY_HTTP_PORT=8090`.

## Run a first simulation

1. In the **Graph Editor**, choose the architecture (*Hierarchical* or
   *Spyker*). Load a predefined topology from the database or build your own
   from the node library on the left.
2. Adjust node settings (client count, compute factor, bandwidth) and link
   settings (latency, packet loss) directly on the canvas. Structural errors are
   reported while you edit.
3. Press **Start simulation**, set the **Seed set** and the **Time limit (s)**
   in virtual seconds, and submit the run.
4. Switch to the **Dashboard** to follow the run's status and learning curves.
   Use **Export CSV** to download the results once the run has finished.

The first run downloads CIFAR-10, which can take a few minutes. A short time
limit (for example 60 seconds) keeps the first run quick.

## Everyday commands

```bash
docker compose ps                 # show service status
docker compose logs -f backend    # follow backend logs
docker compose logs -f ray        # follow simulation worker logs
docker compose restart backend    # restart the API after configuration changes
docker compose down               # stop everything (data in var/ is kept)
docker compose up -d --build      # rebuild and start after pulling updates
```

Runtime data is stored in `var/`: the SQLite database, datasets, checkpoints,
telemetry logs and CSV exports. `docker compose down` keeps it. To start from a
clean state, stop the stack and delete `var/`.

## GPU deployment

With a compatible NVIDIA driver and Docker GPU support:

```bash
docker compose -f compose.yaml -f compose.gpu.yaml up -d --build
docker compose -f compose.yaml -f compose.gpu.yaml down
```

Client training runs on CPU; the GPU is used for evaluation. See
[Operations](operations.md#nvidia-gpus) for driver requirements.

## Local development

Without Docker, run the API and the frontend directly:

```bash
python -m pip install uv==0.13.7
uv sync --locked --extra cpu --extra dev
uv run --no-sync python -m uvicorn fedsim.api.app:app --reload
```

```bash
cd frontend
npm install --global npm@12.2.2
npm ci
npm start
```

The API documentation is then at [localhost:8000/docs](http://localhost:8000/docs)
and the frontend at [localhost:4200](http://localhost:4200). Versions and
details are in [Development](development.md).

## Run the checks

```bash
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check src tests
uv run --no-sync python -m ruff format --check src tests
```

```bash
cd frontend
npm test -- --watch=false
npm run build
```

The same checks run in GitHub Actions on every push to `main` and on pull requests.

## Scripted experiments

For repeatable comparisons, the campaign tool plans and runs paired experiments
through the API and archives every result with checksums:

```bash
uv run --no-sync python -m fedsim.experiments.campaign plan --config experiments/local-pilot.json --calibrate --output var/campaigns/calibration-plan
```

See [Experiments](experiments.md) for the full workflow, including calibration
and archiving.

## Troubleshooting

| Problem | What to do |
| --- | --- |
| Port 8088 is already in use | Set `DEPLOY_HTTP_PORT` in a root `.env` file and run `docker compose up -d` again. |
| A run fails with `fedsim_requires_available_cpu` | Another run is using all Ray CPUs; wait for it to finish. |
| The machine runs out of memory with many clients | Limit concurrent workers with `FEDSIM_CPU_WORKERS` under the backend service's `environment` in `compose.yaml`, or reduce the client count. |
| The first run seems stuck | It is likely downloading CIFAR-10; check `docker compose logs -f ray`. |

More details on configuration, storage and capacity are in [Operations](operations.md).
