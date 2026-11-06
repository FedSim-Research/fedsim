# Development

## Python

Use Python 3.12. From the repository root:

```bash
python -m venv .venv
# Linux / macOS
source .venv/bin/activate
# Windows PowerShell
# .venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
python -m pytest
python -m ruff check src tests
python -m ruff format --check src tests
```

The editable installation makes `fedsim` importable without modifying `sys.path`
or setting `PYTHONPATH`. Python dependencies are declared in `pyproject.toml`.
For a CPU-only PyTorch installation, install `torch` and `torchvision` from
`https://download.pytorch.org/whl/cpu` before installing FedSim.

Start the API:

```bash
python -m uvicorn fedsim.api.app:app --reload
```

The API documentation is available at [localhost:8000/docs](http://localhost:8000/docs).
The API initializes the SQLite schema and default topologies at startup.
Submitting a simulation starts or connects to Ray; importing the package does
not start a Ray cluster or download datasets.

## Frontend

Use Node.js 22.12 or later in the 22.x release line, or Node.js 24, with npm.
The lockfile records frontend dependencies.

```bash
cd frontend
npm ci
npm start
```

Open [localhost:4200](http://localhost:4200). The frontend uses the local API at
port 8000 during development. Run its checks from `frontend/`:

```bash
npm test -- --watch=false
npm run build
```

Tests use temporary local state and synthetic inputs. They do not require a
GPU, download training data, or establish the validity of research results.

The GitHub Actions workflow runs the Python checks, wheel build, Compose
validation, frontend tests, and production frontend build on pushes to `main`
and pull requests.
