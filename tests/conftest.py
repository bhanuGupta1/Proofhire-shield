"""pytest configuration + Phase-3 DB fixtures."""
import os
import sys

# Make backend/ importable for every test module (avoids per-file sys.path hacks
# in future test files; existing files do their own setup so they remain working).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from db_models import Base


@pytest.fixture
def db_session():
    """In-memory SQLite session with the Phase-3 tables created.

    SQLite is used for unit-test speed; production targets Postgres on Neon. The
    sa.Uuid + sa.JSON portable types behave consistently across both dialects
    (UUIDs round-trip via TEXT in SQLite, JSON via TEXT)."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        future=True,
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, future=True
    )
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()
