from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, Response
from contextlib import asynccontextmanager
import ray
from backend.api.api import router
from backend.db import database
from backend.services.default_graph_seed import ensure_default_graphs
from backend.services.simulation_run_queue import run_queue


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    ensure_default_graphs()
    run_queue.start()
    yield
    run_queue.stop()
    if ray.is_initialized():
        ray.shutdown()

# This initializes the main backend server.
# Start the backend from the code root with: uvicorn backend.main:app --reload
# Swagger UI: http://127.0.0.1:8000/docs
app = FastAPI(lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:4200", "http://127.0.0.1:4200"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse(url="/docs", status_code=307)


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


app.include_router(router)
