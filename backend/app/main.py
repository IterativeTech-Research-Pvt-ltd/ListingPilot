from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base, check_connection
from app.api.v1.api import api_router
from app.models import Product, ListingDraft  # Ensure models are imported for Base.metadata.create_all


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Refuse to start without the database rather than serve requests that can't reach it
    check_connection()
    Base.metadata.create_all(bind=engine)
    print(f"[ListingPilot] Connected to the database ({engine.url.host}/{engine.url.database}).", flush=True)
    yield


app = FastAPI(
    lifespan=lifespan,
    title=settings.PROJECT_NAME,
    description="Marketplace listing automation engine for Amazon, Flipkart, and Meesho",
    version="1.0.0",
    openapi_url=f"{settings.API_V1_STR}/openapi.json",
    docs_url=f"{settings.API_V1_STR}/docs",
    redoc_url=f"{settings.API_V1_STR}/redoc",
)

from fastapi.staticfiles import StaticFiles
from pathlib import Path
import os

UPLOAD_DIR = Path(__file__).resolve().parents[1] / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

import time
from fastapi import Request

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    # The dashboard names downloaded exports from this header
    expose_headers=["Content-Disposition"],
)

@app.middleware("http")
async def log_requests(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 1)
    print(f"[{request.method}] {request.url.path} -> {response.status_code} ({duration_ms}ms)", flush=True)
    return response

app.include_router(api_router, prefix=settings.API_V1_STR)
app.mount("/static/uploads", StaticFiles(directory=str(UPLOAD_DIR)), name="uploads")

@app.get("/")
def root():
    return {
        "message": "Welcome to ListingPilot API",
        "docs": f"{settings.API_V1_STR}/docs",
        "phase": 3,
        "status": "online"
    }
