"""pytest configuration + Phase-3 DB fixtures."""
import os
import sys

# Make backend/ importable for every test module (avoids per-file sys.path hacks
# in future test files; existing files do their own setup so they remain working).
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from db_models import Base


@pytest.fixture
def db_session():
    """In-memory SQLite session with the Phase-3 tables created.

    StaticPool keeps a single shared connection — without it each `sqlite:///:memory:`
    checkout opens a fresh in-memory DB and the tables created by `create_all`
    aren't visible to the endpoint that subsequently writes through the same
    session. Production targets Postgres on Neon."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
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


@pytest.fixture
def client_with_db(db_session):
    """FastAPI TestClient whose `get_db` dependency yields the in-memory SQLite
    session from `db_session`, so endpoints persist into a real session that the
    test can also query directly."""
    from fastapi.testclient import TestClient
    from db import get_db
    from main import app

    def _override():
        yield db_session

    app.dependency_overrides[get_db] = _override
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_db, None)
