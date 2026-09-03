"""
infrastructure/database/session.py
────────────────────────────────────
SQLAlchemy session factory — Supabase PostgreSQL backend.

Reads connection URL from:
  1. st.secrets["SUPABASE_DB_URL"]   (Streamlit Cloud)
  2. os.environ["SUPABASE_DB_URL"]   (local .env / shell)
  3. Hardcoded fallback               (dev only — remove in prod)
"""

import os
from contextlib import contextmanager

import streamlit as st
from sqlalchemy import create_engine, event, text
from sqlalchemy.orm import sessionmaker, declarative_base

# ─────────────────────────────────────────────────────────────────────────────
#  Connection URL resolution
# ─────────────────────────────────────────────────────────────────────────────

def _get_db_url() -> str:
    # 1. Streamlit secrets (production / Streamlit Cloud)
    try:
        url = st.secrets.get("SUPABASE_DB_URL")
        if url:
            return url
            
        # Fallback to individual [postgres] table in Streamlit secrets
        if "postgres" in st.secrets:
            pg = st.secrets["postgres"]
            return (
                f"postgresql+psycopg2://{pg['user']}:{pg['password']}"
                f"@{pg['host']}:{pg['port']}/{pg['database']}?sslmode=require"
            )
    except (KeyError, FileNotFoundError, AttributeError):
        pass

    # 2. Environment variable (local dev with .env)
    url = os.environ.get("SUPABASE_DB_URL", "")
    if url:
        return url

    # 3. Hardcoded fallback — REMOVE BEFORE COMMITTING TO GIT
    return (
        "postgresql+psycopg2://postgres:7vZqYen4xbYPwhVP"
        "@db.dincofyibvidfiubiqnn.supabase.co:6543/postgres?sslmode=require"
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Engine — connection pool tuned for Supabase (PgBouncer-aware)
# ─────────────────────────────────────────────────────────────────────────────

_DB_URL = _get_db_url()

# Supabase uses PgBouncer in transaction-pooling mode by default.
# We must set:
#   pool_pre_ping     → detect stale connections
#   connect_args      → keep_alives to avoid idle timeouts
#   pool_size         → keep small (free tier has connection limits)
#   max_overflow      → extra connections allowed beyond pool_size

_engine = create_engine(
    _DB_URL,
    pool_pre_ping=True,
    pool_size=5,
    max_overflow=10,
    pool_timeout=30,
    pool_recycle=1800,          # recycle connections every 30 min
    connect_args={
        "connect_timeout":    10,
        "application_name":   "manifest_app",
        "keepalives":         1,
        "keepalives_idle":    30,
        "keepalives_interval": 5,
        "keepalives_count":   5,
        "options":            "-c statement_timeout=60000",  # 60s query timeout
    },
    echo=False,                 # set True to log SQL in dev
)


# ─────────────────────────────────────────────────────────────────────────────
#  Session factory
# ─────────────────────────────────────────────────────────────────────────────

_SessionFactory = sessionmaker(bind=_engine, autocommit=False, autoflush=False)

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
    session = _SessionFactory()
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
    Safe to call multiple times (uses CREATE TABLE IF NOT EXISTS semantics).
    """
    # Import models here to ensure they are registered on Base before create_all
    from infrastructure.database import models  # noqa: F401
    Base.metadata.create_all(bind=_engine)


def get_engine():
    """Return the shared engine (useful for pd.read_sql)."""
    return _engine


def test_connection() -> tuple[bool, str]:
    """
    Ping the database.  Returns (True, version_string) or (False, error_msg).
    Useful for a health-check page.
    """
    try:
        with _engine.connect() as conn:
            result = conn.execute(text("SELECT version()"))
            version = result.scalar()
        return True, version
    except Exception as exc:
        return False, str(exc)
