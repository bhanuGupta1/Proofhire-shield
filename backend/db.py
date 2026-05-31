"""
SQLAlchemy 2.x engine + session + FastAPI dependency.

Persistence is OPTIONAL. If DATABASE_URL is unset, this module exposes a
SessionLocal that is None and get_db() yields None — endpoints treat persistence
as a no-op and behave exactly as they did in Phase 1/2. This keeps the demo /
local-dev / anonymous flows working without a database.
"""
from __future__ import annotations

import os
from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

DATABASE_URL = os.environ.get("DATABASE_URL")

if DATABASE_URL:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True, future=True)
    SessionLocal = sessionmaker(
        autocommit=False, autoflush=False, bind=engine, future=True
    )
else:
    engine = None
    SessionLocal = None


def is_db_available() -> bool:
    """True if DATABASE_URL is configured and the SessionLocal factory is ready."""
    return SessionLocal is not None


def get_db() -> Generator[Session | None, None, None]:
    """FastAPI dependency: yields a Session, or None if DB is not configured.

    Endpoints MUST handle the None case — when persistence is unavailable, they
    fall back to today's stateless behaviour.
    """
    if SessionLocal is None:
        yield None
        return
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
