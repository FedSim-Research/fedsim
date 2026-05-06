# Federated Learning Simulation in Geo-Distributed Settings (FedSim)

FedSim is a graph-based federated learning simulation platform with a FastAPI backend, an Angular frontend, and two simulation engines (Hierarchical FL and Spyker FL).

## Repository Overview

- [`code/backend/`](code/backend): FastAPI API, persistence layer, simulation orchestration
- [`code/frontend/`](code/frontend): Angular UI (graph editor + simulation start flow)
- [`code/framework/impl/`](code/framework/impl): Simulation implementations (Hierarchical, Spyker)
- [`code/framework/flower/framework/`](code/framework/flower/framework): local Flower framework fork

See [`code/README.md`](code/README.md) for a compact code directory overview.

- Open the port in the server firewall (example with `ufw`):

```bash
sudo ufw allow 8088/tcp
```

You can change the port inside [`docker-compose.yml`](code/docker-compose.yml)

URLs:

- Frontend URL: `http://<SERVER-IP>:8088`  
  (Port mapping is defined in `code/docker-compose.yml` at the nginx `ports` entry: `${DEPLOY_HTTP_PORT:-8088}:80`.)
- Grafana URL: `http://<SERVER-IP>:8088/grafana/`
- Ray URL: `http://<SERVER-IP>:8088/ray/`


## One-Command Docker Startup (No GPU-Support)

```bash
cd code
docker compose -f docker-compose.yml up -d
```


## One-Command Docker Startup (With GPU-Support)

GPU allocation is configured per simulation run via the frontend/API `gpu_budget` setting. 

Note that GPU currently only supports evaluation.

```bash
cd code
docker compose -f docker-compose.yml -f docker-compose.gpu.yml up -d
```

##  Stop Containers

```bash
cd code
docker compose -f docker-compose.yml down
```
or
```bash
docker compose -f docker-compose.yml -f docker-compose.gpu.yml down
```

## Debugging

View logs:

- Single service (example: backend):

```bash
cd code
docker compose logs -f fedsim-backend-deploy
```

- All services:

```bash
cd code
docker compose logs -f
```

## Rebuild containers from scratch:
- Without GPU-Support:
```bash
cd code
docker compose -f docker-compose.yml down --remove-orphans
docker compose -f docker-compose.yml build --no-cache
docker compose -f docker-compose.yml up -d
```
- With GPU-Support:
```bash
cd code
docker compose -f docker-compose.yml -f docker-compose.gpu.yml down --remove-orphans
docker compose -f docker-compose.yml -f docker-compose.gpu.yml build --no-cache
docker compose -f docker-compose.yml up -d
```