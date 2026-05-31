"""Tests for backend/db.py + db_models.py — Phase-3 persistence skeleton."""
import importlib
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from db_models import Assessment, Base, Scan


# ── Schema invariants ────────────────────────────────────────────────────────

def test_both_tables_in_metadata():
    table_names = set(Base.metadata.tables.keys())
    assert "scans" in table_names
    assert "assessments" in table_names


def test_assessment_has_fk_to_scan():
    fks = list(Assessment.__table__.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "scans"
    assert fk.column.name == "id"
    # CASCADE on delete so orphan assessments cannot survive a scan being removed.
    assert (fk.ondelete or "").upper() == "CASCADE"


def test_safe_copy_only_no_original_text_column():
    """Privacy: only safe_copy_text is persisted. The raw original_text is never
    stored — it contains the real PII the scanner flagged."""
    cols = {c.name for c in Scan.__table__.columns}
    assert "safe_copy_text" in cols
    assert "original_text" not in cols


def test_scan_id_is_uuid_not_integer():
    """Per Bhanu 2026-05-31: UUIDs, no sequential integers."""
    id_col = Scan.__table__.columns["id"]
    # SQLAlchemy 2.0 sa.Uuid maps to UUID on Postgres / CHAR(32) on SQLite. The
    # python_type is uuid.UUID either way.
    import uuid as _uuid
    assert id_col.type.python_type is _uuid.UUID


def test_phase4_user_id_column_present_on_both_tables():
    """Phase 4: each row optionally carries the Clerk user_id (sub claim)."""
    scan_cols = {c.name for c in Scan.__table__.columns}
    assessment_cols = {c.name for c in Assessment.__table__.columns}
    assert "user_id" in scan_cols
    assert "user_id" in assessment_cols
    # Nullable so Phase-3 rows survive without backfill.
    assert Scan.__table__.columns["user_id"].nullable is True
    assert Assessment.__table__.columns["user_id"].nullable is True


# ── In-memory SQLite round-trips (uses conftest.db_session fixture) ──────────

def test_persist_scan_round_trip(db_session):
    scan = Scan(
        filename="cv.pdf",
        risk_level="GREEN",
        risk_score=10,
        prompt_injection_findings=[],
        pii_findings=[{"pii_type": "email", "matched_text": "x@y.com"}],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.1,
        safe_copy_text="Cleaned CV text.",
        summary="No issues detected.",
        match_analysis={"skills": {}, "experience_tier": "Entry"},
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    assert scan.id is not None
    loaded = db_session.query(Scan).filter_by(id=scan.id).first()
    assert loaded is not None
    assert loaded.filename == "cv.pdf"
    assert loaded.match_analysis["experience_tier"] == "Entry"
    assert loaded.pii_findings[0]["pii_type"] == "email"


def test_persist_assessment_with_scan_fk(db_session):
    scan = Scan(
        filename="cv.pdf",
        risk_level="GREEN",
        risk_score=0,
        prompt_injection_findings=[],
        pii_findings=[],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.0,
        safe_copy_text="cleaned",
        summary="ok",
        match_analysis={},
    )
    db_session.add(scan)
    db_session.commit()

    assessment = Assessment(
        scan_id=scan.id,
        framework="ProofHire v1 — heuristic scoring",
        headline="Strong candidate",
        dimensions=[{"name": "X", "text": "Y", "bullets": []}],
        overall_recommendation="Worth interviewing",
        overall_score=75,
        next_steps=["a", "b", "c"],
        provider_used="anthropic",
    )
    db_session.add(assessment)
    db_session.commit()
    loaded = db_session.query(Assessment).filter_by(scan_id=scan.id).first()
    assert loaded is not None
    assert loaded.overall_score == 75
    assert loaded.provider_used == "anthropic"


# ── Optional-DB behaviour (db.py contract) ────────────────────────────────────

def test_db_is_unavailable_when_url_unset(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import db
    importlib.reload(db)
    assert db.is_db_available() is False
    gen = db.get_db()
    val = next(gen)
    assert val is None


def test_db_is_available_when_url_set(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "sqlite:///:memory:")
    import db
    importlib.reload(db)
    assert db.is_db_available() is True
    # Reset for subsequent tests.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(db)
