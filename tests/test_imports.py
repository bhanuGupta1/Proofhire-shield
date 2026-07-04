"""Unit + API tests for Phase 8 import."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from importer import clean_candidate, clean_job, plan_candidate_import


# ── Unit ─────────────────────────────────────────────────────────────────────

def test_clean_candidate_aliases_and_requires_name():
    c = clean_candidate({"name": "  Ada  ", "role": "Engineer"})
    assert c == {
        "full_name": "Ada",
        "email": None,
        "phone": None,
        "headline": "Engineer",
        "location": None,
    }
    assert clean_candidate({"email": "x@y.com"}) is None


def test_clean_job_parses_skills_csv():
    j = clean_job({"title": "Dev", "skills": "python, go , "})
    assert j["required_skills"] == ["python", "go"]


def test_plan_dedupes_within_batch_and_against_existing():
    rows = [
        {"name": "A", "email": "a@x.com"},
        {"name": "A2", "email": "A@x.com"},  # dup (case-insensitive)
        {"name": "B", "email": "existing@x.com"},  # dup vs existing
        {"name": "C"},  # no email — created
    ]
    plan = plan_candidate_import(rows, {"existing@x.com"})
    assert len(plan.to_create) == 2
    assert plan.skipped == 2


# ── API ──────────────────────────────────────────────────────────────────────

def test_import_candidates_creates_and_dedupes(client_with_db_and_auth):
    # Seed one existing candidate by email.
    client_with_db_and_auth.post(
        "/candidates", json={"full_name": "Existing", "email": "dup@x.com"}
    )
    r = client_with_db_and_auth.post(
        "/import/candidates",
        json={
            "rows": [
                {"name": "New One", "email": "new@x.com", "role": "Analyst"},
                {"name": "Dup", "email": "DUP@x.com"},  # skipped
                {"email": "noname@x.com"},  # invalid
            ]
        },
    )
    assert r.status_code == 200, r.text
    assert r.json() == {"created": 1, "skipped": 1, "invalid": 1}
    # The imported candidate is now listed with source=import.
    names = [c["full_name"] for c in client_with_db_and_auth.get("/candidates").json()["candidates"]]
    assert "New One" in names


def test_import_jobs_creates_and_dedupes(client_with_db_and_auth):
    client_with_db_and_auth.post("/jobs", json={"title": "Existing Role", "client_name": "Acme"})
    r = client_with_db_and_auth.post(
        "/import/jobs",
        json={
            "rows": [
                {"title": "Fresh Role", "skills": "python"},
                {"title": "existing role", "client": "acme"},  # dup
                {"client": "no title"},  # invalid
            ]
        },
    )
    assert r.json() == {"created": 1, "skipped": 1, "invalid": 1}


def test_import_writes_audit_entry(client_with_db_and_auth):
    client_with_db_and_auth.post(
        "/import/candidates", json={"rows": [{"name": "Solo"}]}
    )
    actions = [e["action"] for e in client_with_db_and_auth.get("/audit").json()["entries"]]
    assert "candidates.imported" in actions


def test_import_requires_auth(client_with_db):
    r = client_with_db.post("/import/candidates", json={"rows": []})
    assert r.status_code in (401, 403, 503)
