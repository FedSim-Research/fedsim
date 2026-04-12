# RP_FedSim

RP_FedSim is a graph-based federated learning simulation platform with a FastAPI backend, an Angular frontend, and two simulation engines (Hierarchical FL and Spyker FL).

## Repository Overview

- [`code/backend/`](code/backend): FastAPI API, persistence layer, simulation orchestration
- [`code/frontend/`](code/frontend): Angular UI (graph editor + simulation start flow)
- [`code/framework/impl/`](code/framework/impl): Simulation implementations (Hierarchical, Spyker)
- [`code/framework/flower/framework/`](code/framework/flower/framework): local Flower framework fork

See `code/README.md` for a compact code directory overview.

## One-Command Docker Startup (No GPU-Support)

```bash
cd code
sudo docker compose -f docker-compose.yml up -d
```

## One-Command Docker Startup (With GPU-Support)

GPU allocation is configured per simulation run via the frontend/API `gpu_budget` setting.
```bash
cd code
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

Stop everything:

```bash
cd code
docker compose down
```

View logs:

- Single service (example: backend):

```bash
cd code
docker compose logs -f backend
```

- All services:

```bash
cd code
docker compose logs -f
```

URLs:

- Frontend: `http://localhost:4200`
- Backend: `http://localhost:8000`
- Ray Dashboard: `http://localhost:8265`
- Prometheus: `http://localhost:9010`
- Grafana: `http://localhost:3000`
