"""API tests for the Phase 7 append-only audit log."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID


def test_creating_candidate_writes_audit_entry(client_with_db_and_auth):
    client_with_db_and_auth.post("/candidates", json={"full_name": "Ada"})
    audit = client_with_db_and_auth.get("/audit").json()
    actions = [e["action"] for e in audit["entries"]]
    assert "candidate.created" in actions
    entry = next(e for e in audit["entries"] if e["action"] == "candidate.created")
    assert "Ada" in entry["summary"]
    assert entry["entity_type"] == "candidate"


def test_creating_share_writes_audit_entry(client_with_db_and_auth):
    job = client_with_db_and_auth.post("/jobs", json={"title": "Role"}).json()
    client_with_db_and_auth.post(f"/jobs/{job['id']}/share", json={})
    actions = [e["action"] for e in client_with_db_and_auth.get("/audit").json()["entries"]]
    assert "share.created" in actions


def test_audit_is_tenant_scoped(client_with_db_and_auth, db_session):
    from db_models import AuditLog

    db_session.add(
        AuditLog(
            user_id=OTHER_USER_ID,
            action="candidate.created",
            summary="Theirs",
        )
    )
    db_session.commit()
    entries = client_with_db_and_auth.get("/audit").json()["entries"]
    assert all(e["summary"] != "Theirs" for e in entries)


def test_audit_newest_first(client_with_db_and_auth):
    client_with_db_and_auth.post("/candidates", json={"full_name": "First"})
    client_with_db_and_auth.post("/candidates", json={"full_name": "Second"})
    entries = client_with_db_and_auth.get("/audit").json()["entries"]
    # Most recent action appears before the earlier one.
    summaries = [e["summary"] for e in entries]
    assert summaries.index("Candidate 'Second' added (manual).") < summaries.index(
        "Candidate 'First' added (manual)."
    )


def test_audit_requires_auth(client_with_db):
    assert client_with_db.get("/audit").status_code in (401, 403, 503)
