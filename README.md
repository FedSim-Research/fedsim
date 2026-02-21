# RP_FedSim

RP_FedSim is a graph-based federated learning simulation platform with a FastAPI backend, an Angular frontend, and two simulation engines (Hierarchical FL and Spyker FL).

## Prerequisites

- Python 3.10+ (recommended: Python 3.12)
- Node.js + npm (LTS)
- PM2 (for process management, optional)
- Docker + Docker Compose (for Grafana/Prometheus/Loki monitoring stack)

## Repository Overview

- [`code/backend/`](code/backend): FastAPI API, persistence layer, simulation orchestration
- [`code/frontend/`](code/frontend): Angular UI (graph editor + simulation start flow)
- [`code/framework/impl/`](code/framework/impl): Simulation implementations (Hierarchical, Spyker)
- [`code/framework/flower/framework/`](code/framework/flower/framework): local Flower framework fork

See `code/README.md` for a compact code directory overview.

## Backend Setup & Start

From project root:

```bash
cd code
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Run backend directly:

```bash
cd code
source .venv/bin/activate
uvicorn backend.main:app --reload
```

Backend URLs:
- API: `http://localhost:8000`
- Swagger: `http://localhost:8000/docs`

## Frontend Setup & Start

From project root:

```bash
cd code/frontend
npm install
npm run start
```

Frontend URL:
- `http://localhost:4200`

## Service Start with PM2 (optional)

Use this if you want one command to manage backend/frontend/ray processes.

Install PM2 once:

```bash
sudo npm install -g pm2
```

Start backend + frontend + Ray:

```bash
cd code
pm2 start ecosystem.config.js --only backend,frontend,ray
```

Note:
- Ray can also auto-initialize when simulations start from backend-only mode.
- The dedicated `ray` PM2 process is mainly useful for stable dashboard/metrics availability.

Useful PM2 commands:

```bash
pm2 status
pm2 logs
pm2 stop all
```

## Monitoring Services (Grafana + Prometheus + Loki)

Monitoring is configured via Docker Compose to stay portable across Linux/macOS/Windows.

Start:

```bash
cd code
docker compose -f monitoring/docker-compose.yml up -d
```

Stop:

```bash
cd code
docker compose -f monitoring/docker-compose.yml down
```

Monitoring URLs:
- Prometheus: `http://localhost:9010`
- Loki: `http://localhost:3100`
- Grafana: `http://localhost:3000`

### Grafana Dashboard Setup (one-time)

1. Open Grafana: `http://localhost:3000` (`admin` / `admin`)
2. Add Prometheus datasource with URL `http://localhost:9010`
3. Import dashboard: `code/frontend/dashboards/ray-monitoring.json`

## Engine Architecture (for interested readers)

Both engines are integrated through the backend Start-Simulation API and are based on the local Flower stack:

- Hierarchical FL engine: [`code/framework/impl/main/main_hierarchical.py`](code/framework/impl/main/main_hierarchical.py)
- Spyker FL engine: [`code/framework/impl/main/main_spyker.py`](code/framework/impl/main/main_spyker.py)
- Backend entrypoint: [`code/backend/api/routers/simulation.py`](code/backend/api/routers/simulation.py)
- Simulation controller: [`code/backend/simulation_controller.py`](code/backend/simulation_controller.py)

The frontend sends architecture-specific settings to the backend, which maps the graph into the corresponding engine builder and starts the simulation.

### Runtime flow

1. Frontend builds/updates a graph (nodes + edges + configs).
2. Frontend sends `start_simulation` request with architecture-specific parameters.
3. Backend validates graph and payload in `code/backend/api/routers/simulation.py`.
4. `code/backend/simulation_controller.py` dispatches to the correct builder:
   - Hierarchical: [`code/backend/services/hierfl_simulation_builder.py`](code/backend/services/hierfl_simulation_builder.py)
   - Spyker: [`code/backend/services/spyker_simulation_builder.py`](code/backend/services/spyker_simulation_builder.py)
5. Builder maps DB graph to engine objects (`Performance`, `Network`, server/client topology).
6. Engine runs via Ray:
   - Hierarchical runtime: [`code/framework/impl/main/main_hierarchical.py`](code/framework/impl/main/main_hierarchical.py)
   - Spyker runtime: [`code/framework/impl/main/main_spyker.py`](code/framework/impl/main/main_spyker.py)
7. Optional model evaluation returns accuracy/loss in the API response.

### Hierarchical engine structure

- Roles: one `SuperServer` + multiple `EdgeServer` + clients.
- Communication: super server sends global model to edges, edges coordinate clients, aggregated updates flow back to super server.
- Topology expectation: exactly one super server; each client connected to exactly one server.

### Spyker engine structure

- Roles: multiple peer servers + clients (no super server).
- Communication: server mesh + token-based synchronization logic.
- Topology expectation: no super server; each client connected to exactly one server.

## Flower Simulation Setup (Dev / Framework Work)

The Flower simulation stack is Linux-first. On Windows, use WSL2 and run the Linux commands below.

Assumes `.venv` is already created and activated (see Backend setup above).

Verify pip path:
- Linux: `which pip` should point to `<project>/code/.venv/bin/pip`
- PowerShell: `gcm pip` should point to `<project>\\code\\.venv\\Scripts\\pip`

Install local Flower framework in editable mode:

```bash
cd ./code/framework/flower/framework/
pip install -e .
pip install -e ".[simulation]"
```

Note: dependency download can be large (~8GB).

Verify binaries:
- Linux:
  - `which flwr` -> `<project>/code/.venv/bin/flwr`
  - `which flower-simulation` -> `<project>/code/.venv/bin/flower-simulation`
- PowerShell:
  - `gcm flwr` -> `<project>\\code\\.venv\\Scripts\\flwr`
  - `gcm flower-simulation` -> `<project>\\code\\.venv\\Scripts\\flower-simulation`

Optional hard check for local Flower usage:

Temporarily insert at the top of:
`<project>/code/framework/flower/framework/py/flwr/__init__.py`

```python
print("\n" + "="*53)
print(">>> SUCCESS: You are using your CUSTOM LOCAL FLWR <<<")
print("="*53 + "\n")
```

## Run a Flower Simulation

From project root:

```bash
flwr run ./code/framework/impl/
```

The run writes a model file (for example `final_model.pt`) in the working directory.
