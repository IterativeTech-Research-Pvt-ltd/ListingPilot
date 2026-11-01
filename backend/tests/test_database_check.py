import pytest
from sqlalchemy.engine import make_url
from sqlalchemy.exc import OperationalError

from app.core import database


class _UnreachableEngine:
    """Stands in for an engine whose every connect fails with the given driver error."""

    url = make_url("postgresql+psycopg2://u:p@db.example.supabase.co/db")

    def __init__(self, driver_message):
        self.driver_message = driver_message
        self.attempts = 0

    def connect(self):
        self.attempts += 1
        raise OperationalError("SELECT 1", {}, Exception(self.driver_message + "\n"))


@pytest.fixture(autouse=True)
def no_retry_wait(monkeypatch):
    monkeypatch.setattr(database.time, "sleep", lambda _s: None)


def _startup_error(driver_message):
    target = _UnreachableEngine(driver_message)
    with pytest.raises(RuntimeError) as exc:
        database.check_connection(target)
    assert target.attempts == database.DB_CONNECT_ATTEMPTS
    return str(exc.value)


def test_dns_failure_names_dns_not_the_port():
    message = _startup_error(
        'could not translate host name "db.example.supabase.co" to address: Name or service not known'
    )
    assert "db.example.supabase.co:5432" in message
    assert "could not translate host name" in message
    assert "DNS" in message
    assert "blocking port 5432" not in message


def test_timeout_points_at_blocked_port():
    message = _startup_error("connection to server at \"1.2.3.4\", port 5432 failed: timeout expired")
    assert "timeout expired" in message
    assert "blocking port 5432" in message


def test_bad_password_points_at_credentials():
    message = _startup_error('password authentication failed for user "u"')
    assert "credentials in DATABASE_URL" in message


def test_no_ipv6_route_points_at_session_pooler():
    message = _startup_error('connection to server at "2406:da14::1", port 5432 failed: Network is unreachable')
    assert "Session pooler" in message


def test_unknown_error_is_shown_with_generic_hint():
    message = _startup_error("something unexpected")
    assert "something unexpected" in message
    assert "Check DATABASE_URL and your network" in message
