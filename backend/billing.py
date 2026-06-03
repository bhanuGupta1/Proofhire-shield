"""
Billing helpers — Phase 7 monetisation gates.

Two pure helpers used by the route layer to decide free-vs-Pro behaviour:
- is_pro: one row in `subscriptions` with status in PRO_STATUSES and
  current_period_end in the future.
- scans_used_this_month: COUNT of Scan rows authored by the user since the
  start of the current UTC calendar month. Org-shared scans authored by
  colleagues do NOT count — quota tracks who triggered the work, not who
  can see it.

No counter table. Both helpers rely on the existing user_id index.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from db_models import MonthlyUsage, Scan, Subscription


FREE_SCAN_LIMIT = 10
PRO_STATUSES = frozenset({"active", "trialing"})


def _current_period() -> str:
    """UTC 'YYYY-MM' bucket. Calendar month, UTC, no timezone surprises."""
    return datetime.now(timezone.utc).strftime("%Y-%m")


def _start_of_current_month_utc() -> datetime:
    now = datetime.now(timezone.utc)
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def is_pro(user_id: str, db: Session) -> bool:
    """True iff the user has an active Stripe subscription that has not lapsed.

    `incomplete` and `past_due` are explicitly NOT Pro — Stripe will lift them
    to `active` on a successful retry, at which point the next webhook flips
    the row. The period_end comparison runs in the DB so SQLite (tests, which
    drops tzinfo on read) and Postgres (prod, which preserves it) agree.
    """
    now = datetime.now(timezone.utc)
    return (
        db.query(Subscription)
        .filter(Subscription.user_id == user_id)
        .filter(Subscription.status.in_(PRO_STATUSES))
        .filter(Subscription.current_period_end != None)  # noqa: E711
        .filter(Subscription.current_period_end > now)
        .first()
        is not None
    )


def scans_used_this_month(user_id: str, db: Session) -> int:
    return (
        db.query(Scan)
        .filter(Scan.user_id == user_id)
        .filter(Scan.created_at >= _start_of_current_month_utc())
        .count()
    )


def quota_used_this_month(user_id: str, db: Session) -> int:
    """Return the gate-authoritative count for the current UTC month.

    Reads MonthlyUsage (the atomic counter that gates /scan-cv) rather than
    counting Scan rows, so the value the UI shows in /billing/status matches
    what the gate will actually enforce. Pre-8.1 deployments without a row
    for the current month return 0 — see migration 0007 for the deploy-day
    bucket-reset behaviour.
    """
    row = (
        db.query(MonthlyUsage)
        .filter(MonthlyUsage.user_id == user_id)
        .filter(MonthlyUsage.period == _current_period())
        .first()
    )
    return row.count if row is not None else 0


def consume_or_refuse(user_id: str, db: Session) -> bool:
    """Atomically reserve one free-tier scan for this user this month.

    Returns True iff the caller was under the cap and the counter has been
    incremented. False otherwise (caller is at/over FREE_SCAN_LIMIT and
    must be 402'd by the route layer). Pro callers MUST short-circuit
    before calling this — Pro usage is unmetered.

    Race-freedom: composite PK on (user_id, period) makes the INSERT path
    self-serialising; the UPDATE path is a single conditional statement
    (WHERE count < FREE_SCAN_LIMIT), which both Postgres and SQLite execute
    under a row lock so concurrent updates serialise and only the ones that
    observe count below the limit succeed (rowcount==1).
    """
    period = _current_period()
    try:
        db.add(MonthlyUsage(user_id=user_id, period=period, count=1))
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
    result = db.execute(
        update(MonthlyUsage)
        .where(MonthlyUsage.user_id == user_id)
        .where(MonthlyUsage.period == period)
        .where(MonthlyUsage.count < FREE_SCAN_LIMIT)
        .values(
            count=MonthlyUsage.count + 1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return result.rowcount == 1
