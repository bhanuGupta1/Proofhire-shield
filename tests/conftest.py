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


@pytest.fixture(autouse=True)
def _reset_rate_buckets():
    """Phase 8.2 — clear the in-process rate-limiter state between tests so
    one test's 30 anonymous calls don't 429 the next test's first call. The
    limiter itself is exercised by dedicated tests."""
    from rate_limit import reset_for_tests

    reset_for_tests()
    yield
    reset_for_tests()


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


# Phase 4 — Clerk user identity stubbed via dependency_overrides.
TEST_USER_ID = "user_test_phase4"
OTHER_USER_ID = "user_other_phase4"
# Phase 5 — Clerk organisation context.
TEST_ORG_ID = "org_test_phase5"
OTHER_ORG_ID = "org_other_phase5"


@pytest.fixture
def client_with_db_and_auth(client_with_db):
    """TestClient with DB + a stubbed authenticated user. Both
    get_current_user (required) and get_current_user_optional return
    TEST_USER_ID, so endpoints behave as if a real Clerk JWT was verified."""
    from auth import get_current_user, get_current_user_optional
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_user_optional] = lambda: TEST_USER_ID
    try:
        yield client_with_db
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_optional, None)


@pytest.fixture
def client_with_db_auth_and_org(client_with_db):
    """TestClient with DB + authed user + active organisation context.
    get_current_org_optional returns TEST_ORG_ID, so every persistence and
    listing path treats the caller as a member of that org."""
    from auth import get_current_user, get_current_user_optional, get_current_org_optional
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_user_optional] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_org_optional] = lambda: TEST_ORG_ID
    try:
        yield client_with_db
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_optional, None)
        app.dependency_overrides.pop(get_current_org_optional, None)


@pytest.fixture
def client_with_db_auth_org_admin(client_with_db):
    """TestClient with DB + authed user + active org + Clerk org_role=admin.
    Phase 8.4 fixture for the org-Checkout / org-Portal endpoints."""
    from auth import (
        get_current_org_optional,
        get_current_org_role_optional,
        get_current_user,
        get_current_user_optional,
    )
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_user_optional] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_org_optional] = lambda: TEST_ORG_ID
    app.dependency_overrides[get_current_org_role_optional] = lambda: "admin"
    try:
        yield client_with_db
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_optional, None)
        app.dependency_overrides.pop(get_current_org_optional, None)
        app.dependency_overrides.pop(get_current_org_role_optional, None)


@pytest.fixture
def client_with_db_auth_org_viewer(client_with_db):
    """Same as client_with_db_auth_org_admin but org_role=viewer — used to
    verify the admin-only endpoints 403 a non-admin member."""
    from auth import (
        get_current_org_optional,
        get_current_org_role_optional,
        get_current_user,
        get_current_user_optional,
    )
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_user_optional] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_org_optional] = lambda: TEST_ORG_ID
    app.dependency_overrides[get_current_org_role_optional] = lambda: "viewer"
    try:
        yield client_with_db
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_optional, None)
        app.dependency_overrides.pop(get_current_org_optional, None)
        app.dependency_overrides.pop(get_current_org_role_optional, None)


@pytest.fixture
def client_with_auth_only():
    """TestClient with the auth user stubbed but NO database — used to verify
    503 behaviour on endpoints that need a DB to honour the request."""
    from fastapi.testclient import TestClient
    from auth import get_current_user, get_current_user_optional
    from main import app

    app.dependency_overrides[get_current_user] = lambda: TEST_USER_ID
    app.dependency_overrides[get_current_user_optional] = lambda: TEST_USER_ID
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_current_user, None)
        app.dependency_overrides.pop(get_current_user_optional, None)
