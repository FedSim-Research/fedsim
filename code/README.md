# RP-FedSim Code

This directory contains the backend, frontend, and framework code for RP-FedSim.

## Directory layout

- [backend/](backend): FastAPI backend, SQLAlchemy models, and simulation controller.
- [frontend/](frontend): Angular frontend (ngx-vflow graph editor and UI).
- [framework/](framework): Federated learning framework implementation (Spyker and Hierarchical FL) used by the backend, built on [Flower](https://github.com/adap/flower).
- [requirements.txt](requirements.txt): Python dependencies for the backend and frameworks.

## Setup and run

See the [project root README.md](../README.md) for backend/frontend setup and run instructions.

## Notes

- The backend uses SQLite by default and creates the database on startup in
  `code/backend/db/fedsim.db`.
