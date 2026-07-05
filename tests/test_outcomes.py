"""API tests for Phase 9 outcomes + conversion funnel."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID


def _job_and_candidate(client):
    job = client.post("/jobs", json={"title": "Backend"}).json()
    cand = client.post("/candidates", json={"full_name": "Ada"}).json()
    return job, cand


def test_record_and_list_outcome(client_with_db_and_auth):
    job, cand = _job_and_candidate(client_with_db_and_auth)
    r = client_with_db_and_auth.post(
        f"/candidates/{cand['id']}/outcomes",
        json={"job_id": job["id"], "type": "interviewed", "notes": "went well"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["type"] == "interviewed"
    listed = client_with_db_and_auth.get(f"/candidates/{cand['id']}/outcomes").json()
    assert len(listed) == 1
    assert listed[0]["notes"] == "went well"


def test_invalid_outcome_type_rejected(client_with_db_and_auth):
    job, cand = _job_and_candidate(client_with_db_and_auth)
    r = client_with_db_and_auth.post(
        f"/candidates/{cand['id']}/outcomes",
        json={"job_id": job["id"], "type": "promoted"},
    )
    assert r.status_code == 422


def test_outcome_for_other_tenants_job_404(client_with_db_and_auth, db_session):
    from db_models import Job

    _, cand = _job_and_candidate(client_with_db_and_auth)
    other = Job(user_id=OTHER_USER_ID, title="Theirs")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    r = client_with_db_and_auth.post(
        f"/candidates/{cand['id']}/outcomes",
        json={"job_id": str(other.id), "type": "hired"},
    )
    assert r.status_code == 404


def test_tenant_funnel_counts_and_placed(client_with_db_and_auth):
    job, cand = _job_and_candidate(client_with_db_and_auth)
    for t in ["interviewed", "offered", "hired"]:
        client_with_db_and_auth.post(
            f"/candidates/{cand['id']}/outcomes",
            json={"job_id": job["id"], "type": t},
        )
    funnel = client_with_db_and_auth.get("/outcomes/funnel").json()
    assert funnel["counts"]["interviewed"] == 1
    assert funnel["counts"]["hired"] == 1
    assert funnel["total"] == 3
    assert funnel["placed"] == 1  # 'hired' counts as placed


def test_job_funnel_scoped_to_job(client_with_db_and_auth):
    job_a = client_with_db_and_auth.post("/jobs", json={"title": "A"}).json()
    job_b = client_with_db_and_auth.post("/jobs", json={"title": "B"}).json()
    cand = client_with_db_and_auth.post("/candidates", json={"full_name": "C"}).json()
    client_with_db_and_auth.post(
        f"/candidates/{cand['id']}/outcomes",
        json={"job_id": job_a["id"], "type": "hired"},
    )
    fa = client_with_db_and_auth.get(f"/jobs/{job_a['id']}/outcomes/funnel").json()
    fb = client_with_db_and_auth.get(f"/jobs/{job_b['id']}/outcomes/funnel").json()
    assert fa["placed"] == 1
    assert fb["placed"] == 0


def test_outcome_writes_audit(client_with_db_and_auth):
    job, cand = _job_and_candidate(client_with_db_and_auth)
    client_with_db_and_auth.post(
        f"/candidates/{cand['id']}/outcomes",
        json={"job_id": job["id"], "type": "hired"},
    )
    actions = [e["action"] for e in client_with_db_and_auth.get("/audit").json()["entries"]]
    assert "outcome.recorded" in actions


def test_funnel_requires_auth(client_with_db):
    assert client_with_db.get("/outcomes/funnel").status_code in (401, 403, 503)
