import time
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from .config import settings

# A few attempts ride out a brief network blip at startup
DB_CONNECT_TIMEOUT_S = 15
DB_CONNECT_ATTEMPTS = 3


def init_engine():
    """Engine for the PostgreSQL database (Supabase) in DATABASE_URL. There is no other database."""
    raw_url = (settings.DATABASE_URL or "").strip()
    if raw_url.startswith("postgresql://"):
        raw_url = raw_url.replace("postgresql://", "postgresql+psycopg2://", 1)
    elif raw_url.startswith("postgres://"):
        raw_url = raw_url.replace("postgres://", "postgresql+psycopg2://", 1)

    if not raw_url.startswith("postgresql+psycopg2://"):
        raise RuntimeError(
            "DATABASE_URL must be the Supabase PostgreSQL connection string (postgresql://...). "
            "ListingPilot has no local database fallback."
        )

    # create_engine doesn't connect; the first query (or check_connection at startup) does
    return create_engine(
        raw_url,
        connect_args={"connect_timeout": DB_CONNECT_TIMEOUT_S},
        pool_pre_ping=True,
        pool_recycle=300
    )


def _connection_hint(error_text: str) -> str:
    """What to do about a failed connection, based on the driver's error."""
    text = error_text.lower()
    if "could not translate host name" in text:
        return ("The hostname could not be resolved: this network's DNS is not answering for it. "
                "Set DNS to 8.8.8.8 / 1.1.1.1, run ipconfig /flushdns, and restart.")
    if "password authentication failed" in text:
        return "The database rejected the credentials in DATABASE_URL."
    if "network is unreachable" in text:
        return ("This network has no IPv6 route, and Supabase's direct host (db.<ref>.supabase.co) is IPv6-only. "
                "Use the Session pooler connection string from the Supabase dashboard instead.")
    if "timeout expired" in text or "timed out" in text or "connection refused" in text:
        return ("The connection to the database port failed; this network may be blocking port 5432 "
                "(e.g. the co-working space Wi-Fi). Switch networks and restart.")
    return "Check DATABASE_URL and your network, then restart."


def check_connection(target=None):
    """
    Connects once (with a few retries). Raises with a clear message when the database
    can't be reached, instead of continuing without one.
    """
    target = target or engine
    for attempt in range(1, DB_CONNECT_ATTEMPTS + 1):
        try:
            with target.connect():
                return
        except Exception as e:
            if attempt == DB_CONNECT_ATTEMPTS:
                # SQLAlchemy wraps the driver error; its first line is the useful part
                driver_error = str(getattr(e, "orig", None) or e).strip().splitlines()[0]
                raise RuntimeError(
                    f"Cannot reach the database at {target.url.host}:{target.url.port or 5432} "
                    f"after {attempt} attempts: {driver_error}. {_connection_hint(driver_error)}"
                ) from e
            print(f"[ListingPilot] Database not answering (attempt {attempt}); retrying...", flush=True)
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
