"""API tests for the jobs router (platform Phase 1)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID, TEST_ORG_ID


def test_create_job(client_with_db_and_auth):
    r = client_with_db_and_auth.post(
        "/jobs",
        json={
            "title": "Backend Engineer",
            "client_name": "Acme",
            "required_skills": ["python", "fastapi"],
        },
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Backend Engineer"
    assert body["status"] == "open"
    assert body["required_skills"] == ["python", "fastapi"]


def test_create_job_requires_title(client_with_db_and_auth):
    r = client_with_db_and_auth.post("/jobs", json={"title": ""})
    assert r.status_code == 422


def test_create_job_requires_auth(client_with_db):
    # See test_candidates.test_create_requires_auth: unconfigured Clerk in tests
    # yields 503; a deployed instance returns 401. Never created either way.
    r = client_with_db.post("/jobs", json={"title": "X"})
    assert r.status_code in (401, 403, 503)


def test_list_returns_only_callers_jobs(client_with_db_and_auth):
    client_with_db_and_auth.post("/jobs", json={"title": "Mine"})
    r = client_with_db_and_auth.get("/jobs")
    assert r.status_code == 200
    assert r.json()["count"] == 1


def test_list_status_filter(client_with_db_and_auth):
    a = client_with_db_and_auth.post("/jobs", json={"title": "Open Role"}).json()
    client_with_db_and_auth.patch(f"/jobs/{a['id']}", json={"status": "closed"})
    client_with_db_and_auth.post("/jobs", json={"title": "Still Open"})
    r = client_with_db_and_auth.get("/jobs", params={"status": "open"})
    assert r.json()["count"] == 1
    assert r.json()["jobs"][0]["title"] == "Still Open"


def test_get_job_detail(client_with_db_and_auth):
    created = client_with_db_and_auth.post("/jobs", json={"title": "Detail Me"}).json()
    r = client_with_db_and_auth.get(f"/jobs/{created['id']}")
    assert r.status_code == 200
    assert r.json()["title"] == "Detail Me"


def test_detail_cross_tenant_is_404(client_with_db_and_auth, db_session):
    from db_models import Job

    other = Job(user_id=OTHER_USER_ID, title="Not Yours")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    r = client_with_db_and_auth.get(f"/jobs/{other.id}")
    assert r.status_code == 404


def test_update_job(client_with_db_and_auth):
    created = client_with_db_and_auth.post("/jobs", json={"title": "Old"}).json()
    r = client_with_db_and_auth.patch(
        f"/jobs/{created['id']}", json={"title": "New", "status": "on_hold"}
    )
    assert r.status_code == 200
    assert r.json()["title"] == "New"
    assert r.json()["status"] == "on_hold"


def test_update_job_rejects_bad_status(client_with_db_and_auth):
    created = client_with_db_and_auth.post("/jobs", json={"title": "X"}).json()
    r = client_with_db_and_auth.patch(
        f"/jobs/{created['id']}", json={"status": "banana"}
    )
    assert r.status_code == 422


def test_delete_job(client_with_db_and_auth):
    created = client_with_db_and_auth.post("/jobs", json={"title": "Bye"}).json()
    assert client_with_db_and_auth.delete(f"/jobs/{created['id']}").status_code == 204
    assert client_with_db_and_auth.get(f"/jobs/{created['id']}").status_code == 404


def test_org_member_sees_org_job(client_with_db_auth_and_org, db_session):
    from db_models import Job

    shared = Job(user_id=OTHER_USER_ID, org_id=TEST_ORG_ID, title="Org Job")
    db_session.add(shared)
    db_session.commit()
    r = client_with_db_auth_and_org.get("/jobs")
    assert "Org Job" in [j["title"] for j in r.json()["jobs"]]
