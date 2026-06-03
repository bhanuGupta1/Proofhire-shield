"""
In-process token-bucket rate limiter (Phase 8.2).

Single-process design: HF Spaces runs one worker (no horizontal scaling),
so a dict + lock holds bucket state in memory. When / if we go multi-instance,
swap this module's internals to Redis without changing the call sites.

Bucket key: (route, identity).
- Authenticated callers are identified by their Clerk `user_id` (verified
  token claim, never client-controlled).
- Anonymous callers are identified by the client IP (best-effort —
  X-Forwarded-For leftmost when present, else the socket peer).

Rates are per minute. The bucket capacity equals the per-minute rate, so a
fresh caller can burst up to one minute's worth of requests and then is
metered at the steady-state refill rate.

No external dependency. Tests reset the bucket state via `reset_for_tests`.
"""
from __future__ import annotations

import threading
import time


# Per-minute caps — Bhanu's Phase 8 defaults.
ANON_PER_MIN = 30
AUTH_FREE_PER_MIN = 100
AUTH_PRO_PER_MIN = 300


class _TokenBucket:
    """Refills `rate` tokens per second up to `capacity`. One token per request."""

    __slots__ = ("rate", "capacity", "tokens", "last_refill", "_lock")

    def __init__(self, rate_per_sec: float, capacity: float) -> None:
        self.rate = rate_per_sec
        self.capacity = capacity
        self.tokens = capacity
        self.last_refill = time.monotonic()
        self._lock = threading.Lock()

    def consume(self) -> tuple[bool, float]:
        """Try to consume one token. Returns (allowed, retry_after_seconds).

        retry_after_seconds is 0 when allowed; otherwise the wall-clock seconds
        until one token would refill, suitable for the Retry-After response
        header."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self.last_refill
            self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
            self.last_refill = now
            if self.tokens >= 1:
                self.tokens -= 1
                return True, 0.0
            return False, (1 - self.tokens) / self.rate


# Keyed by (route, identity). The dict itself needs a lock because two
# concurrent first-time callers can race the .get + .setdefault on the same key.
_buckets: dict[tuple[str, str], _TokenBucket] = {}
_buckets_lock = threading.Lock()


def _get_or_create(key: tuple[str, str], per_min: int) -> _TokenBucket:
    with _buckets_lock:
        bucket = _buckets.get(key)
        if bucket is None:
            bucket = _TokenBucket(
                rate_per_sec=per_min / 60.0, capacity=float(per_min)
            )
            _buckets[key] = bucket
        return bucket


def check_rate(route: str, identity: str, per_min: int) -> tuple[bool, float]:
    """Public entry point. Returns (allowed, retry_after_seconds)."""
    bucket = _get_or_create((route, identity), per_min)
    return bucket.consume()


def reset_for_tests() -> None:
    """Clear all buckets. Used by the pytest auto-fixture so each test starts
    fresh, regardless of which prior tests scanned through their cap."""
    with _buckets_lock:
        _buckets.clear()
