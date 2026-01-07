# RP-FedSim Code

This directory contains the backend, frontend, and framework code for RP-FedSim.

## Directory layout

- [backend/](backend): FastAPI backend, SQLAlchemy models, and simulation controller.
- [frontend/](frontend): Angular frontend (ngx-vflow graph editor and UI).
- [framework/](framework): Federated learning framework implementation (Spyker and Hierarchical FL) used by the backend, built on [Flower](https://github.com/adap/flower).
- [requirements.txt](requirements.txt): Python dependencies for the backend and frameworks.

## Backend setup (Python)

From the `code/` directory:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Start the backend:

```bash
uvicorn backend.main:app --reload
```

The API is available at `http://127.0.0.1:8000`, and Swagger UI at
`http://127.0.0.1:8000/docs`.

## Frontend setup (Angular)

From the `code/frontend/` directory:

```bash
npm install
npm run start
```

The frontend is available at `http://localhost:4200`.

## Notes

- The backend uses SQLite by default and creates the database on startup in
  `code/backend/db/fedsim.db`.
