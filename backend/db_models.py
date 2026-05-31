"""
SQLAlchemy declarative models for the Phase-3 persistence layer.

Schema decisions (per Bhanu, 2026-05-31):
- UUID primary keys (no sequential integers — opaque from the client side).
- Only safe_copy_text is stored. The raw original_text is NEVER persisted; it
  contains the real PII the scanner flagged. Re-upload to re-scan.
- Portable JSON columns work in Postgres (target) and SQLite (test fixtures);
  if Phase 6 needs JSONB-specific operators we migrate then.
- Assessment.scan_id is a NOT-NULL FK with ON DELETE CASCADE; every assessment
  is anchored to a scan in the same audit chain.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    # Phase 4: Clerk user_id (sub claim). Nullable so the Phase-3 rows that
    # predate auth survive the migration; new rows always set it when an
    # authenticated user is the caller.
    user_id = Column(String(64), nullable=True, index=True)
    # Phase 5: Clerk organization id (when the creator was acting inside an
    # org context). Every member of that org sees scans tagged with the same
    # org_id via the per-org list / detail queries. Nullable so solo users
    # (no active org) and Phase-3/4 rows survive without backfill.
    org_id = Column(String(64), nullable=True, index=True)
    filename = Column(String(256), nullable=False)
    risk_level = Column(String(8), nullable=False)
    risk_score = Column(Integer, nullable=False)
    prompt_injection_findings = Column(JSON, nullable=False, default=list)
    pii_findings = Column(JSON, nullable=False, default=list)
    ai_text_likelihood = Column(String(8), nullable=False)
    ai_text_score = Column(Float, nullable=False)
    safe_copy_text = Column(Text, nullable=False)
    summary = Column(Text, nullable=False)
    match_analysis = Column(JSON, nullable=False)

    assessments = relationship(
        "Assessment", back_populates="scan", cascade="all, delete-orphan"
    )


class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    scan_id = Column(
        Uuid, ForeignKey("scans.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # Phase 4: denormalised Clerk user_id so per-user list/access queries do
    # not always need a join, and so an orphaned Phase-3 scan cannot be silently
    # reassigned by linking a new assessment to it.
    user_id = Column(String(64), nullable=True, index=True)
    # Phase 5: denormalised Clerk org_id with the same rationale as user_id —
    # org-scoped queries (list-my-org's-assessments) avoid an extra join.
    org_id = Column(String(64), nullable=True, index=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    framework = Column(String(64), nullable=False)
    headline = Column(Text, nullable=False)
    dimensions = Column(JSON, nullable=False)
    overall_recommendation = Column(Text, nullable=False)
    overall_score = Column(Integer, nullable=False)
    next_steps = Column(JSON, nullable=False)
    provider_used = Column(String(16), nullable=False)

    scan = relationship("Scan", back_populates="assessments")


class Subscription(Base):
    """One row per user with a Stripe subscription (Phase 7 monetisation).

    Per-user Pro model: user_id is the primary key, so a user owns at most one
    subscription. Cancel-then-resubscribe UPSERTs the existing row rather than
    creating a second one. Org-level Pro is deferred — when it lands it will
    add a parallel `OrganizationSubscription` table, not change this one.
    """

    __tablename__ = "subscriptions"

    # Clerk sub claim; same shape as Scan.user_id / Assessment.user_id (String(64)).
    user_id = Column(String(64), primary_key=True)
    # Stripe `cus_...`. Indexed because the webhook lookups by it when the
    # event metadata doesn't carry our user_id (defensive fallback).
    stripe_customer_id = Column(String(64), nullable=False, index=True)
    # `sub_...`. Nullable to support the brief `incomplete` window between
    # Checkout Session creation and the first `customer.subscription.created`
    # webhook landing.
    stripe_subscription_id = Column(String(64), nullable=True)
    # Currently only 'pro'. Kept as a column so a later "pro+" or "team" plan
    # does not need a migration.
    plan = Column(String(16), nullable=False, default="pro")
    # Stripe's lifecycle: 'active' | 'past_due' | 'canceled' | 'incomplete' |
    # 'incomplete_expired' | 'trialing' | 'unpaid'. We treat ONLY 'active' (or
    # 'trialing') with current_period_end in the future as Pro — see
    # billing.is_pro.
    status = Column(String(24), nullable=False)
    # Nullable: in the 'incomplete' window we may not yet know the period end.
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class WebhookEvent(Base):
    """Stripe webhook idempotency ledger (Phase 7.5).

    Stripe re-delivers an event until it receives a 2xx, so the same `evt_...`
    id can arrive more than once. We record every event id we have fully
    processed and skip any we have already seen, which makes the webhook handler
    idempotent. No business data lives here — just the id, its type, and when we
    first saw it.
    """

    __tablename__ = "webhook_events"

    event_id = Column(String(64), primary_key=True)
    event_type = Column(String(64), nullable=False)
    received_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
