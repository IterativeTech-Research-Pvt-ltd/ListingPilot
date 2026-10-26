"""
Celery Application Initialization (ListingPilot Background Worker Engine)
Provides distributed, multi-tenant background task execution via Redis.
Automatically supports eager execution fallback when Redis is offline in local dev/tests.
"""
import os
from celery import Celery
import redis
from app.core.config import settings


def is_redis_available(url: str, timeout: float = 0.5) -> bool:
    """Checks whether the Redis broker is reachable without blocking."""
    try:
        r = redis.Redis.from_url(url, socket_connect_timeout=timeout, socket_timeout=timeout)
        return bool(r.ping())
    except Exception:
        return False


# Determine if Celery should run tasks synchronously (eager mode)
# If CELERY_TASK_ALWAYS_EAGER is explicitly set, honor it.
# Otherwise, if Redis broker is offline, automatically use eager mode with in-memory broker/backend.
redis_online = is_redis_available(settings.CELERY_BROKER_URL)
eager_mode = settings.CELERY_TASK_ALWAYS_EAGER or not redis_online

broker_url = settings.CELERY_BROKER_URL if redis_online else "memory://"
result_backend = settings.CELERY_RESULT_BACKEND if redis_online else "cache+memory://"

celery_app = Celery(
    "listingpilot",
    broker=broker_url,
    backend=result_backend,
)

celery_app.conf.update(
    task_always_eager=eager_mode,
    task_eager_propagates=True,
    task_store_eager_result=True,
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Kolkata",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    worker_prefetch_multiplier=1,
)

celery_app.autodiscover_tasks(["app.tasks.batch_tasks"])
