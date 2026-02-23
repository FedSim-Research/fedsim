# RP_FedSim

RP_FedSim is a graph-based federated learning simulation platform with a FastAPI backend, an Angular frontend, and two simulation engines (Hierarchical FL and Spyker FL).

## Prerequisites

- Python 3.10+ (recommended: Python 3.12)
- Node.js + npm (LTS)
- Docker + Docker Compose (for Grafana/Prometheus/Loki monitoring stack)

## Repository Overview

- [`code/backend/`](code/backend): FastAPI API, persistence layer, simulation orchestration
- [`code/frontend/`](code/frontend): Angular UI (graph editor + simulation start flow)
- [`code/framework/impl/`](code/framework/impl): Simulation implementations (Hierarchical, Spyker)
- [`code/framework/flower/framework/`](code/framework/flower/framework): local Flower framework fork

See `code/README.md` for a compact code directory overview.

## One-Command Docker Startup

```bash
cd code
sudo docker compose -f docker-compose.yml up -d
```

Stop everything:

```bash
cd code
docker compose down
```

URLs:

- Frontend: `http://localhost:4200`
- Backend: `http://localhost:8000`
- Ray Dashboard: `http://localhost:8265`
- Prometheus: `http://localhost:9010`
- Grafana: `http://localhost:3000`
