"""Schema + round-trip tests for the Candidate and Job models (platform Phase 1)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import uuid

from db_models import Base, Candidate, Job, Scan


# ── Schema invariants ────────────────────────────────────────────────────────

def test_candidate_and_job_tables_in_metadata():
    names = set(Base.metadata.tables.keys())
    assert "candidates" in names
    assert "jobs" in names


def test_candidate_scan_fk_is_set_null_not_cascade():
    """The candidate must OUTLIVE deletion of its origin scan — pipeline history
    is the durable object; the scan is only its provenance."""
    fks = list(Candidate.__table__.foreign_keys)
    assert len(fks) == 1
    fk = fks[0]
    assert fk.column.table.name == "scans"
    assert fk.column.name == "id"
    assert (fk.ondelete or "").upper() == "SET NULL"


def test_candidate_is_tenant_scoped():
    cols = {c.name for c in Candidate.__table__.columns}
    assert "user_id" in cols
    assert "org_id" in cols
    assert Candidate.__table__.columns["user_id"].nullable is True
    assert Candidate.__table__.columns["org_id"].nullable is True


def test_job_is_tenant_scoped():
    cols = {c.name for c in Job.__table__.columns}
    assert "user_id" in cols
    assert "org_id" in cols


def test_candidate_id_is_uuid():
    assert Candidate.__table__.columns["id"].type.python_type is uuid.UUID


# ── Round-trips (conftest.db_session) ────────────────────────────────────────

def test_candidate_round_trip_with_tags_json(db_session):
    cand = Candidate(
        user_id="user_1",
        full_name="Ada Lovelace",
        email="ada@example.com",
        headline="Senior Analyst",
        source="manual",
        tags=["python", "sql"],
    )
    db_session.add(cand)
    db_session.commit()
    db_session.refresh(cand)
    loaded = db_session.query(Candidate).filter_by(id=cand.id).first()
    assert loaded is not None
    assert loaded.full_name == "Ada Lovelace"
    assert loaded.status == "new"  # server/default applied
    assert loaded.source == "manual"
    assert loaded.tags == ["python", "sql"]


def test_candidate_links_to_scan(db_session):
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

    cand = Candidate(user_id="user_1", full_name="From Scan", scan_id=scan.id)
    db_session.add(cand)
    db_session.commit()
    db_session.refresh(cand)
    assert cand.scan is not None
    assert cand.scan.filename == "cv.pdf"


def test_job_round_trip_with_required_skills_json(db_session):
    job = Job(
        user_id="user_1",
        title="Backend Engineer",
        client_name="Acme",
        required_skills=["python", "fastapi", "postgres"],
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)
    loaded = db_session.query(Job).filter_by(id=job.id).first()
    assert loaded is not None
    assert loaded.title == "Backend Engineer"
    assert loaded.status == "open"  # default
    assert loaded.required_skills == ["python", "fastapi", "postgres"]
