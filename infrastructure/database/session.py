"""
infrastructure/database/session.py
────────────────────────────────────
SQLAlchemy session factory — Supabase PostgreSQL backend.

Supabase exposes two ports:
  • 5432  → direct connection  (supports keepalives, prepared statements)
  • 6543  → PgBouncer pooler   (transaction mode — limited feature set)

We use port 5432 with NullPool for Streamlit (stateless, re-entrant env).
"""

import os
from contextlib import contextmanager

import streamlit as st
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.pool import NullPool

# ─────────────────────────────────────────────────────────────────────────────
#  Connection URL resolution
# ─────────────────────────────────────────────────────────────────────────────

def _get_db_url() -> str:
    """
    Resolution order:
      1. st.secrets["postgres"]  table  (Streamlit Cloud secrets.toml)
      2. SUPABASE_DB_URL env var         (local .env / shell)
      3. Raise — never silently use hardcoded creds in prod
    """
    # 1. Streamlit secrets [postgres] table
    try:
        pg = st.secrets.get("postgres")
        if pg:
            host = pg["host"]
            user = pg["user"]
            password = pg["password"]
            database = pg["dbname"]          # note: "dbname" not "database"
            # Use port 5432 (direct) — avoids PgBouncer quirks
            port = pg.get("port", 5432)
            return (
                f"postgresql+psycopg2://{user}:{password}"
                f"@{host}:{port}/{database}?sslmode=require"
            )
    except (KeyError, FileNotFoundError, AttributeError):
        pass

    # 2. Environment variable
    url = os.environ.get("SUPABASE_DB_URL", "").strip()
    if url:
        return url

    # 3. Hard fail — do not silently fall back to hardcoded credentials
    raise RuntimeError(
        "Database URL not configured. "
        "Add a [postgres] section to .streamlit/secrets.toml or "
        "set the SUPABASE_DB_URL environment variable."
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Engine
# ─────────────────────────────────────────────────────────────────────────────

def _build_engine():
    """
    Build SQLAlchemy engine with settings appropriate for Supabase + Streamlit.

    Why NullPool?
    Streamlit reruns the script on every interaction. A persistent connection
    pool can accumulate stale/leaked connections across reruns, especially on
    Streamlit Cloud where the process may be shared. NullPool opens a fresh
    connection per operation and closes it immediately — safer and avoids
    exceeding Supabase free-tier connection limits.

    If you need performance, switch to QueuePool with pool_size=2, max_overflow=3
    and add @st.cache_resource around the engine creation.
    """
    url = _get_db_url()

    # connect_args for DIRECT connections (port 5432)
    # Do NOT use these with PgBouncer port 6543
    connect_args = {
        "connect_timeout":     10,
        "application_name":    "manifest_app",
        "sslmode":             "require",
        # TCP keepalives — only valid on direct connections
        "keepalives":          1,
        "keepalives_idle":     30,
        "keepalives_interval": 5,
        "keepalives_count":    5,
    }

    return create_engine(
        url,
        poolclass=NullPool,          # no persistent pool — safe for Streamlit
        connect_args=connect_args,
        echo=False,                  # set True to log SQL in dev
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Cached engine + session factory
#  @st.cache_resource ensures a single instance per Streamlit session server
# ─────────────────────────────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _get_engine():
    return _build_engine()


def _get_session_factory():
    return sessionmaker(
        bind=_get_engine(),
        autocommit=False,
        autoflush=False,
    )


# Shared declarative base — import this in models.py
Base = declarative_base()


# ─────────────────────────────────────────────────────────────────────────────
#  Public helpers
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def get_session():
    """
    Yield a SQLAlchemy session, committing on success or rolling back on error.

    Usage:
        with get_session() as session:
            session.add(some_object)
    """
    factory = _get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def init_db():
    """
    Create all tables defined in models.py if they do not exist yet.
    Safe to call multiple times (CREATE TABLE IF NOT EXISTS semantics).
    """
    from infrastructure.database import models  # noqa: F401 — registers models on Base
    Base.metadata.create_all(bind=_get_engine())


def get_engine():
    """Return the shared engine (useful for pd.read_sql, Alembic, etc.)."""
    return _get_engine()


def test_connection() -> tuple[bool, str]:
    """
    Ping the database.
    Returns (True, version_string) or (False, error_message).
    """
    try:
        with _get_engine().connect() as conn:
            version = conn.execute(text("SELECT version()")).scalar()
        return True, version
    except Exception as exc:
        return False, str(exc)
