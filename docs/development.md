# Development

## Python

Use Python 3.14.10 and uv 0.13.7. The project also supports Python 3.12 and 3.13;
Ray does not yet publish wheels for Python 3.15. `.python-version` selects the
runtime and `uv.lock` records the resolved dependencies, including CPU and CUDA
variants of PyTorch.

From the repository root:

```bash
python -m pip install uv==0.13.7
uv sync --locked --extra cpu --extra dev
uv run --no-sync python -m pytest
uv run --no-sync python -m ruff check src tests
uv run --no-sync python -m ruff format --check src tests
uv pip check
```

uv installs the selected Python version if needed and creates the project
`.venv/`. The editable installation makes `fedsim` importable without modifying
`sys.path` or setting `PYTHONPATH`. The CPU extra selects PyTorch's CPU wheels;
the GPU extra selects CUDA 13.2 wheels. These extras are mutually exclusive.

Start the API:

```bash
uv run --no-sync python -m uvicorn fedsim.api.app:app --reload
```

The API documentation is available at [localhost:8000/docs](http://localhost:8000/docs).
The API initializes the SQLite schema and default topologies at startup.
Submitting a simulation starts or connects to Ray; importing the package does
not start a Ray cluster or download datasets.

To update dependencies intentionally, edit `pyproject.toml`, run
`uv lock --upgrade`, and repeat the checks. Keep `--locked` in CI and deployment so
installation fails when declarations and the lockfile disagree.

## Frontend

Use Node.js 26.13.0 LTS, recorded in `frontend/.nvmrc`, and npm 12.2.2, recorded in
`frontend/package.json`. Node.js 24.15 or later in the 24.x line is also supported.
The npm lockfile records the resolved frontend dependencies.

The frontend uses the latest compatible Angular 21 patch with PrimeNG 21's MIT
release, MIT-licensed PrimeUI themes, and PrimeIcons 7. PrimeNG 22 and its related
packages require a different license model. Keep this boundary when updating the
UI stack; Angular 21's build tooling also requires TypeScript 5.9 and Vitest 4.

```bash
cd frontend
npm install --global npm@12.2.2
npm ci
npm start
```

npm 12 requires explicit approval of dependency installation scripts. The
`allowScripts` entries in `package.json` cover the pinned native build tools used
by Angular. Review and update these entries when those tools change.

Open [localhost:4200](http://localhost:4200). The frontend uses the local API at
port 8000 during development. Run its checks from `frontend/`:

```bash
npm test -- --watch=false
npm run build
```

The Vitest configuration disables Node's native Web Storage in test workers so
jsdom supplies browser storage, including on Node.js 26.

Tests use temporary local state and synthetic inputs. They do not require a GPU
or download training datasets. See [Reproducibility](reproducibility.md) for
experiment records and the distinction between software tests and research
validation.

The GitHub Actions workflow uses the same runtime version files and lockfiles to
run Python checks, distribution builds, Compose validation, frontend tests, and
the production frontend build on pushes to `main` and pull requests.
