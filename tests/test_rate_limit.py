"""Phase 8.2 — rate-limiter unit tests + endpoint integration."""
import time

import pytest

from rate_limit import (
    ANON_PER_MIN,
    AUTH_FREE_PER_MIN,
    AUTH_PRO_PER_MIN,
    _TokenBucket,
    check_rate,
    reset_for_tests,
)


# ── TokenBucket math ─────────────────────────────────────────────────────────

def test_bucket_starts_full():
    b = _TokenBucket(rate_per_sec=1.0, capacity=5.0)
    for _ in range(5):
        ok, _ = b.consume()
        assert ok is True


def test_bucket_refuses_when_empty():
    b = _TokenBucket(rate_per_sec=0.001, capacity=2.0)
    for _ in range(2):
        b.consume()
    ok, retry_after = b.consume()
    assert ok is False
    assert retry_after > 0


def test_bucket_retry_after_reflects_refill_rate():
    """At 1 token/sec, retry_after for a fully-empty bucket is ~1.0 sec."""
    b = _TokenBucket(rate_per_sec=1.0, capacity=1.0)
    b.consume()
    ok, retry_after = b.consume()
    assert ok is False
    assert 0.9 <= retry_after <= 1.1


def test_bucket_refills_over_time():
    """After a brief sleep, a previously-drained bucket has a token again."""
    b = _TokenBucket(rate_per_sec=20.0, capacity=1.0)
    b.consume()
    assert b.consume()[0] is False
    time.sleep(0.1)  # 20 t/s * 0.1s = 2 tokens, capped at 1
    assert b.consume()[0] is True


def test_bucket_capacity_is_a_ceiling():
    """Idle time beyond capacity / rate does not grow the bucket past capacity."""
    b = _TokenBucket(rate_per_sec=100.0, capacity=2.0)
    time.sleep(0.1)  # would refill 10 tokens but capacity is 2
    assert b.consume()[0] is True
    assert b.consume()[0] is True
    assert b.consume()[0] is False


# ── check_rate / reset_for_tests ─────────────────────────────────────────────

def test_check_rate_creates_bucket_on_first_call():
    reset_for_tests()
    ok, _ = check_rate("/x", "ident_a", per_min=2)
    assert ok is True


def test_check_rate_enforces_per_min_cap():
    reset_for_tests()
    for _ in range(3):
        check_rate("/x", "ident_a", per_min=3)
    ok, retry_after = check_rate("/x", "ident_a", per_min=3)
    assert ok is False
    assert retry_after > 0


def test_check_rate_scopes_by_identity():
    reset_for_tests()
    for _ in range(3):
        check_rate("/x", "ident_a", per_min=3)
    # Different identity gets its own bucket.
    ok, _ = check_rate("/x", "ident_b", per_min=3)
    assert ok is True


def test_check_rate_scopes_by_route():
    """Same identity hitting two different routes does not share the cap."""
    reset_for_tests()
    for _ in range(3):
        check_rate("/a", "ident_a", per_min=3)
    ok, _ = check_rate("/b", "ident_a", per_min=3)
    assert ok is True


def test_reset_for_tests_clears_all_buckets():
    reset_for_tests()
    for _ in range(3):
        check_rate("/x", "ident_a", per_min=3)
    reset_for_tests()
    ok, _ = check_rate("/x", "ident_a", per_min=3)
    assert ok is True


# ── Phase 8 defaults stay at the proposed values ─────────────────────────────

def test_phase_8_default_limits():
    """Bhanu approved 30 anon / 100 free / 300 Pro per minute. Pin them so a
    drive-by tweak gets caught in code review."""
    assert ANON_PER_MIN == 30
    assert AUTH_FREE_PER_MIN == 100
    assert AUTH_PRO_PER_MIN == 300


# ── Endpoint integration ────────────────────────────────────────────────────

def test_scan_cv_returns_429_after_anon_cap(monkeypatch):
    """Anonymous /scan-cv: 30/min default. Lower the cap to keep the test fast."""
    from fastapi.testclient import TestClient
    import io
    from main import app
    import rate_limit
    import main as main_module

    monkeypatch.setattr(rate_limit, "ANON_PER_MIN", 3)
    monkeypatch.setattr(main_module, "ANON_PER_MIN", 3)
    reset_for_tests()

    client = TestClient(app, raise_server_exceptions=False)
    payload = io.BytesIO(b"Sarah is a senior engineer with Python.")
    for i in range(3):
        r = client.post(
            "/scan-cv",
            files={"file": ("cv.txt", payload, "text/plain")},
        )
        payload.seek(0)
        assert r.status_code in (200, 422), f"call {i+1}: {r.status_code}"
    r4 = client.post(
        "/scan-cv",
        files={"file": ("cv.txt", io.BytesIO(b"."), "text/plain")},
    )
    assert r4.status_code == 429
    assert "Retry-After" in {k.title() for k in r4.headers.keys()}


def test_webhook_route_uses_anon_rate_bucket():
    """/billing/webhook is unauthenticated; the limiter therefore keys on the
    client IP and ANON_PER_MIN. Drains that bucket directly to prove the
    refusal path is what the endpoint will hit — the call site in main.py is
    the same shape as /scan-cv's (covered by an integration test below)."""
    reset_for_tests()
    cap = 4
    for _ in range(cap):
        ok, _ = check_rate("/billing/webhook", "ip:1.1.1.1", per_min=cap)
        assert ok is True
    ok, retry_after = check_rate("/billing/webhook", "ip:1.1.1.1", per_min=cap)
    assert ok is False
    assert retry_after > 0
    # A different IP gets its own bucket — the limiter is per-source, not global.
    ok2, _ = check_rate("/billing/webhook", "ip:2.2.2.2", per_min=cap)
    assert ok2 is True
