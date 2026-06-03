"""Phase 8.6 — request-id middleware + structured log keys."""
import io
import logging
import re

import pytest
from fastapi.testclient import TestClient

from main import _REQUEST_CTX_FILTER, _push_request_context, _request_ctx, app


client = TestClient(app, raise_server_exceptions=False)
DEMO_DIR = __import__("pathlib").Path(__file__).parent.parent / "demo-cvs"

_UUID_HEX = re.compile(r"^[0-9a-f]{32}$")


# ── Middleware ───────────────────────────────────────────────────────────────

def test_response_carries_x_request_id_header():
    r = client.get("/health")
    assert r.status_code == 200
    rid = r.headers.get("x-request-id")
    assert rid is not None
    assert _UUID_HEX.match(rid), f"unexpected request_id format: {rid}"


def test_each_response_gets_a_unique_request_id():
    rids = {client.get("/health").headers["x-request-id"] for _ in range(5)}
    assert len(rids) == 5


def test_inbound_x_request_id_is_honoured():
    """If the caller / upstream proxy sends X-Request-Id, we echo it back
    instead of generating a new one — that's how distributed-trace
    correlation works across services."""
    rid = "trace-abc-123"
    r = client.get("/health", headers={"x-request-id": rid})
    assert r.headers["x-request-id"] == rid


def test_inbound_x_request_id_is_capped_at_64_chars():
    """A hostile client cannot stuff a megabyte into our log lines via
    X-Request-Id — anything over 64 chars is truncated."""
    rid = "x" * 200
    r = client.get("/health", headers={"x-request-id": rid})
    assert len(r.headers["x-request-id"]) == 64


def test_error_responses_also_carry_x_request_id():
    """The 411 from limit_body_size happens INSIDE call_next; the outer
    request_id_middleware must still attach the header."""
    # Force a POST without Content-Length → middleware returns 411 before
    # any endpoint runs. (TestClient adds Content-Length by default, so we
    # use a GET-with-empty-body trick via the 405 path on a POST endpoint.)
    r = client.get("/scan-cv")
    # 405 (method not allowed) goes through routing -> middleware still wraps.
    assert "x-request-id" in r.headers


# ── Logging filter ───────────────────────────────────────────────────────────

def test_log_record_gets_request_id_attribute():
    """Inside an active request context, log records have request_id / user_id /
    org_id set by the filter. Outside a request, they default to '-'."""
    _request_ctx.set({"request_id": "rid_test_123", "user_id": "u1", "org_id": "o1"})
    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    handler = _Capture()
    handler.addFilter(_REQUEST_CTX_FILTER)
    logging.getLogger().addHandler(handler)
    try:
        logging.getLogger("test").warning("hello")
    finally:
        logging.getLogger().removeHandler(handler)
        _request_ctx.set({})

    assert captured
    rec = captured[-1]
    assert rec.request_id == "rid_test_123"
    assert rec.user_id == "u1"
    assert rec.org_id == "o1"


def test_log_record_defaults_when_no_context():
    captured: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            captured.append(record)

    _request_ctx.set({})
    handler = _Capture()
    handler.addFilter(_REQUEST_CTX_FILTER)
    logging.getLogger().addHandler(handler)
    try:
        logging.getLogger("test").warning("no context")
    finally:
        logging.getLogger().removeHandler(handler)

    assert captured
    rec = captured[-1]
    assert rec.request_id == "-"
    assert rec.user_id == "-"
    assert rec.org_id == "-"


def test_push_request_context_merges_fields():
    """Endpoints push user_id / org_id once Clerk deps resolve. Subsequent
    pushes are additive."""
    _request_ctx.set({"request_id": "rid_a"})
    _push_request_context(user_id="user_x")
    _push_request_context(org_id="org_y")
    ctx = _request_ctx.get()
    assert ctx["request_id"] == "rid_a"  # untouched
    assert ctx["user_id"] == "user_x"
    assert ctx["org_id"] == "org_y"
    _request_ctx.set({})


def test_push_request_context_ignores_empty_values():
    """Anonymous callers pass user_id='' so the filter still shows '-'."""
    _request_ctx.set({"request_id": "rid_b"})
    _push_request_context(user_id="", org_id="")
    ctx = _request_ctx.get()
    assert "user_id" not in ctx
    assert "org_id" not in ctx
    _request_ctx.set({})
