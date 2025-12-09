from fastapi import FastAPI
from backend.api import router

# This initializes the main backend server.
# Swagger UI:     http://127.0.0.1:8000/docs
app = FastAPI()
app.include_router(router)