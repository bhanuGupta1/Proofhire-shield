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
    created_at = Column(DateTime(timezone=True), default=_utc_now, nullable=False)
    framework = Column(String(64), nullable=False)
    headline = Column(Text, nullable=False)
    dimensions = Column(JSON, nullable=False)
    overall_recommendation = Column(Text, nullable=False)
    overall_score = Column(Integer, nullable=False)
    next_steps = Column(JSON, nullable=False)
    provider_used = Column(String(16), nullable=False)

    scan = relationship("Scan", back_populates="assessments")
