"""Tests for backend/auth.py — Clerk JWT verification.

These never make a real network call to Clerk. The full PyJWKClient path is
stubbed via monkeypatching `auth._verify_token`."""
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import jwt as pyjwt
import pytest
from fastapi import HTTPException

import auth


@pytest.fixture
def configured_auth():
    """Set CLERK_* env vars, reload the auth module so its module-level
    constants pick them up, yield, then revert + reload so subsequent tests
    see the unconfigured state."""
    os.environ["CLERK_ISSUER"] = "https://test.clerk.dev"
    os.environ["CLERK_JWKS_URL"] = "https://test.clerk.dev/.well-known/jwks.json"
    importlib.reload(auth)
    try:
        yield auth
    finally:
        os.environ.pop("CLERK_ISSUER", None)
        os.environ.pop("CLERK_JWKS_URL", None)
        importlib.reload(auth)


# ── is_auth_configured ───────────────────────────────────────────────────────

def test_is_auth_configured_false_when_env_missing():
    os.environ.pop("CLERK_ISSUER", None)
    os.environ.pop("CLERK_JWKS_URL", None)
    importlib.reload(auth)
    assert auth.is_auth_configured() is False


def test_is_auth_configured_true_when_env_set(configured_auth):
    assert configured_auth.is_auth_configured() is True


# ── _extract_bearer ──────────────────────────────────────────────────────────

def test_extract_bearer_valid():
    assert auth._extract_bearer("Bearer abc.def.ghi") == "abc.def.ghi"
    assert auth._extract_bearer("bearer abc") == "abc"  # case-insensitive scheme


def test_extract_bearer_invalid():
    assert auth._extract_bearer(None) is None
    assert auth._extract_bearer("") is None
    assert auth._extract_bearer("abc") is None  # no Bearer prefix
    assert auth._extract_bearer("Bearer ") is None  # empty token


# ── get_current_user (required) ──────────────────────────────────────────────

def test_get_current_user_503_when_not_configured():
    os.environ.pop("CLERK_ISSUER", None)
    os.environ.pop("CLERK_JWKS_URL", None)
    importlib.reload(auth)
    with pytest.raises(HTTPException) as exc:
        auth.get_current_user(authorization="Bearer x")
    assert exc.value.status_code == 503


def test_get_current_user_401_when_no_token(configured_auth):
    with pytest.raises(HTTPException) as exc:
        configured_auth.get_current_user(authorization=None)
    assert exc.value.status_code == 401


def test_get_current_user_401_when_malformed_header(configured_auth):
    with pytest.raises(HTTPException) as exc:
        configured_auth.get_current_user(authorization="Token abc")
    assert exc.value.status_code == 401


def test_get_current_user_401_when_token_invalid(configured_auth, monkeypatch):
    def fake(token):
        raise pyjwt.InvalidTokenError("bad")

    monkeypatch.setattr(configured_auth, "_verify_token", fake)
    with pytest.raises(HTTPException) as exc:
        configured_auth.get_current_user(authorization="Bearer abc.def.ghi")
    assert exc.value.status_code == 401


def test_get_current_user_401_when_token_missing_sub(configured_auth, monkeypatch):
    monkeypatch.setattr(configured_auth, "_verify_token", lambda t: {})
    with pytest.raises(HTTPException) as exc:
        configured_auth.get_current_user(authorization="Bearer abc")
    assert exc.value.status_code == 401


def test_get_current_user_returns_user_id_on_valid_token(configured_auth, monkeypatch):
    monkeypatch.setattr(configured_auth, "_verify_token", lambda t: {"sub": "user_test123"})
    assert configured_auth.get_current_user(authorization="Bearer abc.def.ghi") == "user_test123"


# ── get_current_user_optional ────────────────────────────────────────────────

def test_get_current_user_optional_returns_none_when_unconfigured():
    os.environ.pop("CLERK_ISSUER", None)
    os.environ.pop("CLERK_JWKS_URL", None)
    importlib.reload(auth)
    assert auth.get_current_user_optional(authorization="Bearer abc") is None


def test_get_current_user_optional_returns_none_on_no_token(configured_auth):
    assert configured_auth.get_current_user_optional(authorization=None) is None


def test_get_current_user_optional_returns_none_on_malformed(configured_auth):
    assert configured_auth.get_current_user_optional(authorization="Token abc") is None


def test_get_current_user_optional_returns_user_on_valid(configured_auth, monkeypatch):
    monkeypatch.setattr(configured_auth, "_verify_token", lambda t: {"sub": "user_42"})
    assert configured_auth.get_current_user_optional(authorization="Bearer t") == "user_42"


def test_get_current_user_optional_returns_none_on_invalid_token(configured_auth, monkeypatch):
    def fake(token):
        raise pyjwt.InvalidTokenError("bad")

    monkeypatch.setattr(configured_auth, "_verify_token", fake)
    assert configured_auth.get_current_user_optional(authorization="Bearer x") is None
