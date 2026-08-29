
# infrastructure/database/session.py
from contextlib import contextmanager
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker
import os
from infrastructure.database.models import Base

# Ensure the database is created in the project root
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "database.sqlite")
DB_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(DB_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False)

def _migrate_schema():
    """Add columns introduced after the initial schema (SQLite has no ALTER DROP)."""
    insp = inspect(engine)
    if "manifest_lines" not in insp.get_table_names():
        return
    cols = {c["name"] for c in insp.get_columns("manifest_lines")}
    if "type" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE manifest_lines ADD COLUMN type VARCHAR"))


def init_db():
    Base.metadata.create_all(engine)
    _migrate_schema()

@contextmanager
def get_session():
    """Context manager to ensure the DB session is closed correctly."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
