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
docker compose -f docker-compose.yml up -d
```

## One-Command Docker Startup (With GPU-Support)

GPU allocation is configured per simulation run via the frontend/API `gpu_budget` setting.
```bash
cd code
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

## Server Deployment (Nginx Included)

Use the deployment compose file if you want to run everything on a server without installing Nginx manually on the host.

CPU deploy:

```bash
cd code
docker compose -f docker-compose.deploy.yml up -d
```

GPU deploy (requires NVIDIA driver + NVIDIA Container Toolkit on the server):

```bash
cd code
docker compose -f docker-compose.deploy.yml -f docker-compose.gpu.yml up -d
```

- Frontend URL: `http://<SERVER-IP>:8088`  
  (Port mapping is defined in `code/docker-compose.deploy.yml` at the nginx `ports` entry: `${DEPLOY_HTTP_PORT:-8088}:80`.)
- Grafana URL: `http://<SERVER-IP>:8088/grafana/`
- Ray URL: `http://<SERVER-IP>:8088/ray/`
- Prometheus URL: `http://<SERVER-IP>:8088/prometheus/`

- Open the port in the server firewall (example with `ufw`):

```bash
sudo ufw allow 8088/tcp
```

Stop containers (use the same compose files as for `up`):

```bash
cd code
docker compose -f docker-compose.yml down --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.gpu.yml down --remove-orphans
docker compose -f docker-compose.deploy.yml down --remove-orphans
docker compose -f docker-compose.deploy.yml -f docker-compose.gpu.yml down --remove-orphans
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
