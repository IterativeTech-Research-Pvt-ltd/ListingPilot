from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.database import engine, Base
from app.api.v1.api import api_router
from app.models import Product, ListingDraft  # Ensure models are imported for Base.metadata.create_all

# Create tables
try:
    Base.metadata.create_all(bind=engine)
except Exception as e:
    print(f"Database table initialization notice: {e}")

app = FastAPI(
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

# Set up CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
