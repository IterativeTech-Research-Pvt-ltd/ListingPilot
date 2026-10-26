import socket
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from urllib.parse import urlparse
from .config import settings


def init_engine():
    """Initializes direct connection to the Neon Cloud PostgreSQL database."""
    raw_url = settings.DATABASE_URL or ""
    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)

    parsed = urlparse(raw_url)
    neon_host = parsed.hostname or "ep-shy-rain-b4yrdu7z-pooler.c-6.us-east-2.aws.neon.tech"

    # Pre-flight reachability check
    is_reachable = False
    try:
        with socket.create_connection((neon_host, 5432), timeout=2.5):
            is_reachable = True
        print(f"[ListingPilot] Connected directly to Neon Cloud DB ({neon_host}:5432).")
    except Exception:
        print("\n" + "=" * 78)
        print("[ListingPilot Network Notice] Could not reach Neon PostgreSQL on port 5432.")
        print("Please confirm you are NOT connected to the co-working space Wi-Fi (port 5432 is blocked there).")
        print("Falling back to local SQLite database (test_pilot.db) so development continues uninterrupted.")
        print("=" * 78 + "\n")

    if not is_reachable:
        return create_engine(
            "sqlite:///./test_pilot.db",
            connect_args={"check_same_thread": False}
        )

    return create_engine(
        raw_url,
        connect_args={"connect_timeout": 3},
        pool_pre_ping=True,
        pool_recycle=300
    )


engine = init_engine()
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
