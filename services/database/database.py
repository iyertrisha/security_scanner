"""
Database engine, session, and base — shared across all services.

Uses DATABASE_URL from environment (defaults to local PostgreSQL).
For testing, override with SQLite in-memory via get_engine().

Local development: if Postgres is unreachable (wrong role / DB down) and
NETGUARD_SQLITE_FALLBACK allows it, falls back to a file SQLite DB so the
stack runs without Docker. Set NETGUARD_SQLITE_FALLBACK=0 to fail fast instead.
"""

import logging
import os

from sqlalchemy import create_engine, text
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, DeclarativeBase

logger = logging.getLogger("netguard.database")

DEFAULT_LOCAL_PG_URL = "postgresql://netguard:netguard@localhost:5432/netguard"


def get_database_url() -> str:
    """Get database URL from environment, with a sensible default."""
    return os.getenv(
        "DATABASE_URL",
        DEFAULT_LOCAL_PG_URL,
    )


def _project_root_dir() -> str:
    """Project root .../mini-project (parent of ``services``)."""
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def _sqlite_fallback_file_url() -> str:
    db_path = os.path.join(_project_root_dir(), ".netguard_dev.sqlite")
    # SQLAlchemy wants absolute paths for SQLite on-disk.
    return f"sqlite:///{db_path}"


def _sqlite_fallback_allowed(configured_url: str) -> bool:
    raw = os.getenv("NETGUARD_SQLITE_FALLBACK", "auto").strip().lower()
    if raw in ("0", "false", "no", "off", "never"):
        return False
    if raw in ("1", "true", "yes", "on", "always"):
        return True
    # auto: only when user still points at the documented local Docker-style URL
    return configured_url.rstrip("/") == DEFAULT_LOCAL_PG_URL.rstrip("/")


def get_engine(url: str | None = None):
    """Create a SQLAlchemy engine. Pass a URL to override (useful for tests)."""
    resolved = url or get_database_url()
    if resolved.startswith("sqlite"):
        connect_args = {"check_same_thread": False}
        # In-memory SQLite (tests) keeps default threading behavior.
        if ":memory:" in resolved:
            connect_args = {}
        return create_engine(resolved, connect_args=connect_args)
    # pool_pre_ping helps recover stale connections after DB restarts
    return create_engine(resolved, pool_pre_ping=True)


def _probe_connection(eng):
    """Open one connection — fails if Postgres role/DB/auth is invalid."""
    with eng.connect() as conn:
        conn.execute(text("SELECT 1"))


class Base(DeclarativeBase):
    """Base class for all ORM models."""
    pass


def _create_default_engine():
    """Build engine; probe Postgres once and optionally fall back to SQLite on disk."""
    configured = get_database_url()
    eng = get_engine(configured)
    try:
        _probe_connection(eng)
        return eng
    except OperationalError as exc:
        if not _sqlite_fallback_allowed(configured):
            logger.error(
                "PostgreSQL unreachable at configured DATABASE_URL (%s): %s",
                configured.split("@")[-1] if "@" in configured else configured,
                exc,
            )
            raise
        sqlite_url = _sqlite_fallback_file_url()
        logger.warning(
            "PostgreSQL unavailable (%s). Using SQLite fallback at %s. "
            "For Postgres instead: docker compose up -d db, or create role "
            "netguard/password netguard/database netguard, or set "
            "NETGUARD_SQLITE_FALLBACK=0 to disable this fallback.",
            exc,
            sqlite_url,
        )
        os.environ["DATABASE_URL"] = sqlite_url
        return get_engine(sqlite_url)


# Default session factory (can be overridden in tests)
engine = _create_default_engine()
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """FastAPI dependency that yields a DB session and closes it after."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
