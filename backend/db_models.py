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
    # Phase 7.7 — created-timestamp of the Stripe event that last touched this
    # row. The webhook handler ignores any inbound event older than this so an
    # out-of-order `customer.subscription.updated` cannot resurrect Pro access
    # after a `customer.subscription.deleted` has already been processed.
    # Nullable so rows from before the migration survive without backfill.
    last_event_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class OrganizationSubscription(Base):
    """Phase 8.3 — one row per Clerk organization with a Stripe subscription.

    Mirrors `Subscription` but keyed on Clerk `org_id`. Org-level Pro grants
    Pro features to EVERY member of the org while the sub is active (per
    Bhanu's Phase-8 answer #3). Membership changes are out of scope for
    Phase 8 — Codex P7 round-2 MED noted, Phase 9 will add a Clerk
    membership webhook. The active org is the one whose id Clerk stamps on
    the verified JWT as `org_id`.

    Webhooks route subscription events into the right table by the
    `metadata.scope` field stamped at Checkout: `scope=org` lands here,
    everything else lands in the per-user `Subscription` table (Phase 8.5).
    """

    __tablename__ = "org_subscriptions"

    # Clerk org_id, same shape as Scan.org_id (String(64)).
    org_id = Column(String(64), primary_key=True)
    # Stripe `cus_...`. Indexed for the customer-id fallback webhook lookup.
    stripe_customer_id = Column(String(64), nullable=False, index=True)
    stripe_subscription_id = Column(String(64), nullable=True)
    plan = Column(String(16), nullable=False, default="pro")
    status = Column(String(24), nullable=False)
    current_period_end = Column(DateTime(timezone=True), nullable=True)
    # Same out-of-order rejection mechanism as personal Subscription (Phase 7.7).
    last_event_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class MonthlyUsage(Base):
    """Atomic per-user monthly scan-quota counter (Phase 8.1).

    Replaces the Phase-7 count-then-check pattern (Codex P7 round-2 MED) that
    raced under concurrent /scan-cv calls. The composite PK on (user_id,
    period) lets the DB itself serialise concurrent reservations: the gate
    runs INSERT first, then falls back to an UPDATE-WHERE-count<limit when
    the row exists. Both Postgres (production) and SQLite (tests) lock the
    target row during UPDATE, so concurrent callers serialise and only
    those who land before count == FREE_SCAN_LIMIT succeed.

    Pro callers short-circuit BEFORE hitting this table — Pro usage is
    unmetered and not tracked here.
    """

    __tablename__ = "monthly_usage"

    # Clerk sub.
    user_id = Column(String(64), primary_key=True)
    # UTC calendar month as 'YYYY-MM'. String, not date, so sorting / equality
    # comparisons are direct and the column is the same shape on every DB.
    period = Column(String(7), primary_key=True)
    count = Column(Integer, nullable=False, default=0)
    # Phase 9 — separate counter for Pro-tier-style /assessment quota. Lives
    # on the same row so the existing per-user/per-month composite PK keeps
    # both reservations on a single lockable row. Default 0 + migration 0009
    # adds the column with the same server-side default for pre-existing rows.
    assessments_used = Column(Integer, nullable=False, default=0, server_default="0")
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )


class Candidate(Base):
    """A person tracked in the recruiter's pipeline (platform Phase 1).

    A candidate is normally *promoted from a scan* — the scan is the security
    audit anchor, so `scan_id` records how this person entered the system
    (which CV was scanned, with what risk findings). It is nullable + SET NULL
    on scan delete: a candidate outlives the deletion of their scan (the
    pipeline history must survive), but we record the provenance while it
    exists. Candidates created manually (no CV) carry scan_id = NULL and
    source != 'scan'.

    Tenant scoping mirrors Scan/Assessment: user_id owns the row, org_id (when
    the creator acted inside a Clerk org) makes it visible to every org member.
    """

    __tablename__ = "candidates"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(String(64), nullable=True, index=True)
    org_id = Column(String(64), nullable=True, index=True)
    # SET NULL (not CASCADE): deleting the underlying scan must NOT delete the
    # candidate — the pipeline record is the durable business object; the scan
    # is its origin evidence.
    scan_id = Column(
        Uuid, ForeignKey("scans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    full_name = Column(String(256), nullable=False)
    email = Column(String(256), nullable=True)
    phone = Column(String(64), nullable=True)
    headline = Column(String(256), nullable=True)
    location = Column(String(128), nullable=True)
    # 'scan' (promoted from a CV scan) | 'manual' | later: 'import'.
    source = Column(String(32), nullable=False, default="scan")
    # Free-form pipeline status until Phase 2 introduces per-job stages:
    # 'new' | 'reviewing' | 'shortlisted' | 'rejected' | 'hired'.
    status = Column(String(24), nullable=False, default="new")
    notes = Column(Text, nullable=True)
    tags = Column(JSON, nullable=False, default=list)
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_utc_now, onupdate=_utc_now, nullable=False
    )

    scan = relationship("Scan")


class Job(Base):
    """A role / requisition the recruiter is filling (platform Phase 1).

    No FK to candidates yet — the candidate↔job relationship (placements,
    pipeline stages, shortlists) lands in Phase 2 as its own association tables
    so a candidate can sit in several jobs' pipelines at once. Tenant scoping is
    identical to Candidate.
    """

    __tablename__ = "jobs"

    id = Column(Uuid, primary_key=True, default=uuid.uuid4)
    user_id = Column(String(64), nullable=True, index=True)
    org_id = Column(String(64), nullable=True, index=True)
    title = Column(String(256), nullable=False)
    client_name = Column(String(256), nullable=True)
    location = Column(String(128), nullable=True)
    employment_type = Column(String(32), nullable=True)
    seniority = Column(String(32), nullable=True)
    description = Column(Text, nullable=False, default="")
    required_skills = Column(JSON, nullable=False, default=list)
    # 'open' | 'on_hold' | 'closed' | 'filled'.
    status = Column(String(24), nullable=False, default="open")
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
