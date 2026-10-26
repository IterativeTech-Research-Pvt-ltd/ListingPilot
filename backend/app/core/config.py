from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, List
from pathlib import Path
import os

ROOT_DIR = Path(__file__).resolve().parents[3]

class Settings(BaseSettings):
    PROJECT_NAME: str = "ListingPilot"
    API_V1_STR: str = "/api/v1"
    
    # Database: Exclusively Neon PostgreSQL
    DATABASE_URL: str = ""
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ]
    
    # Brand details default
    DEFAULT_BRAND: str = "Gulmohar Home"
    
    # AI Content Engine (OpenRouter / Claude API)
    AI_PROVIDER: str = "openrouter"  # "openrouter" or "anthropic"
    OPENROUTER_API_KEY: Optional[str] = None
    OPENROUTER_MODEL: str = "minimax/minimax-m3.1-flash"
    ANTHROPIC_API_KEY: Optional[str] = None
    CLAUDE_MODEL: str = "claude-3-5-sonnet-20241022"
    
    # Background Workers & Cache (Celery + Redis)
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"
    CELERY_TASK_ALWAYS_EAGER: bool = False
    
    # Amazon SP-API (Phase 2)
    AMAZON_SELLER_ID: Optional[str] = None
    AMAZON_MARKETPLACE_ID: str = "A21TJRUUN4KGV"  # Amazon.in
    AMAZON_SP_API_CLIENT_ID: Optional[str] = None
    AMAZON_SP_API_CLIENT_SECRET: Optional[str] = None
    AMAZON_SP_API_REFRESH_TOKEN: Optional[str] = None
    AMAZON_AWS_ACCESS_KEY: Optional[str] = None
    AMAZON_AWS_SECRET_KEY: Optional[str] = None
    AMAZON_AWS_ROLE_ARN: Optional[str] = None
    
    # Flipkart API (Phase 3)
    FLIPKART_APP_ID: Optional[str] = None
    FLIPKART_APP_SECRET: Optional[str] = None

    ROOT_DIR: Path = ROOT_DIR

    model_config = SettingsConfigDict(
        case_sensitive=True,
        env_file=(str(ROOT_DIR / ".env"), ".env"),
        extra="ignore"
    )

settings = Settings()
