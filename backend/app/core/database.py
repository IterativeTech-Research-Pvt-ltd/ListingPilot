import time
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

# Neon suspends idle compute; the first connection afterwards waits while it wakes up
NEON_CONNECT_TIMEOUT_S = 15
NEON_CONNECT_ATTEMPTS = 3


def init_engine():
    """Engine for the Neon PostgreSQL database in DATABASE_URL. There is no other database."""
    raw_url = (settings.DATABASE_URL or "").strip()
    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)

    if not raw_url.startswith("postgresql+psycopg2://"):
        raise RuntimeError(
            "DATABASE_URL must be the Neon PostgreSQL connection string (postgresql://...). "
            "ListingPilot has no local database fallback."
        )

    # create_engine doesn't connect; the first query (or check_connection at startup) does
    return create_engine(
        raw_url,
        connect_args={"connect_timeout": NEON_CONNECT_TIMEOUT_S},
        pool_pre_ping=True,
        pool_recycle=300
    )


def check_connection(target=None):
    """
    Connects once (retrying while an idle Neon compute wakes up). Raises with a clear message
    when Neon can't be reached, instead of continuing without a database.
    """
    target = target or engine
    for attempt in range(1, NEON_CONNECT_ATTEMPTS + 1):
        try:
            with target.connect():
                return
        except Exception as e:
            if attempt == NEON_CONNECT_ATTEMPTS:
                raise RuntimeError(
                    f"Cannot reach the Neon database at {target.url.host}:{target.url.port or 5432} "
                    f"after {attempt} attempts ({type(e).__name__}). Port 5432 is blocked on the "
                    "co-working space Wi-Fi; switch networks and restart."
                ) from e
            print(f"[ListingPilot] Neon not answering (attempt {attempt}); it may be waking from idle, retrying...", flush=True)
            time.sleep(2)


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
