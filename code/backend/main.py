from fastapi import FastAPI
from contextlib import asynccontextmanager
from backend.api.api import router
from backend.db import database


@asynccontextmanager
async def lifespan(app: FastAPI):
    database.init_db()
    yield

# This initializes the main backend server.
# Start the backend from the code root with: uvicorn backend.main:app --reload
# Swagger UI: http://127.0.0.1:8000/docs
app = FastAPI(lifespan=lifespan)
app.include_router(router)