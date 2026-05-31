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

from sqlalchemy.orm import Session

from db_models import Scan, Subscription


FREE_SCAN_LIMIT = 10
PRO_STATUSES = frozenset({"active", "trialing"})


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
