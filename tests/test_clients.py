"""API tests for Phase 5 clients + public share links."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from datetime import datetime, timedelta, timezone

from conftest import OTHER_USER_ID, TEST_USER_ID
from db_models import Candidate, ClientShare, Job, ShortlistEntry


# ── Client CRUD ──────────────────────────────────────────────────────────────

def test_client_crud(client_with_db_and_auth):
    created = client_with_db_and_auth.post(
        "/clients", json={"name": "Acme", "contact_email": "hr@acme.com"}
    )
    assert created.status_code == 201, created.text
    cid = created.json()["id"]

    assert client_with_db_and_auth.get("/clients").json()["count"] == 1
    assert client_with_db_and_auth.get(f"/clients/{cid}").json()["name"] == "Acme"

    upd = client_with_db_and_auth.patch(
        f"/clients/{cid}", json={"contact_name": "Jane"}
    )
    assert upd.json()["contact_name"] == "Jane"

    assert client_with_db_and_auth.delete(f"/clients/{cid}").status_code == 204
    assert client_with_db_and_auth.get(f"/clients/{cid}").status_code == 404


def test_client_cross_tenant_is_404(client_with_db_and_auth, db_session):
    from db_models import Client

    other = Client(user_id=OTHER_USER_ID, name="Theirs")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    assert client_with_db_and_auth.get(f"/clients/{other.id}").status_code == 404


def test_client_requires_auth(client_with_db):
    assert client_with_db.post("/clients", json={"name": "X"}).status_code in (
        401,
        403,
        503,
    )


# ── Share creation (authed) ──────────────────────────────────────────────────

def test_create_share_returns_token_and_path(client_with_db_and_auth):
    job = client_with_db_and_auth.post("/jobs", json={"title": "Role"}).json()
    r = client_with_db_and_auth.post(f"/jobs/{job['id']}/share", json={})
    assert r.status_code == 201, r.text
    body = r.json()
    assert len(body["token"]) > 20
    assert body["path"] == f"/s/{body['token']}"
    assert body["expires_at"] is None
    # Listed for the job.
    shares = client_with_db_and_auth.get(f"/jobs/{job['id']}/shares").json()["shares"]
    assert [s["id"] for s in shares] == [body["id"]]


def test_create_share_for_other_tenant_job_404(client_with_db_and_auth, db_session):
    other = Job(user_id=OTHER_USER_ID, title="Theirs")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    assert (
        client_with_db_and_auth.post(f"/jobs/{other.id}/share", json={}).status_code
        == 404
    )


def test_revoke_share_makes_it_gone(client_with_db_and_auth):
    job = client_with_db_and_auth.post("/jobs", json={"title": "Role"}).json()
    share = client_with_db_and_auth.post(f"/jobs/{job['id']}/share", json={}).json()
    assert client_with_db_and_auth.delete(f"/shares/{share['id']}").status_code == 204
    assert client_with_db_and_auth.get(f"/jobs/{job['id']}/shares").json()["shares"] == []


# ── Public share view (NO auth) ──────────────────────────────────────────────

def _seed_share(db, *, expires_at=None, user=TEST_USER_ID):
    job = Job(user_id=user, title="Backend", client_name="Acme")
    db.add(job)
    db.commit()
    db.refresh(job)
    cand = Candidate(user_id=user, full_name="Grace Hopper", source="manual")
    db.add(cand)
    db.commit()
    db.refresh(cand)
    db.add(ShortlistEntry(user_id=user, job_id=job.id, candidate_id=cand.id))
    share = ClientShare(
        user_id=user, job_id=job.id, token="tok_" + "x" * 20, expires_at=expires_at
    )
    db.add(share)
    db.commit()
    db.refresh(share)
    return share


def test_public_share_returns_shortlist_without_auth(client_with_db, db_session):
    share = _seed_share(db_session)
    r = client_with_db.get(f"/share/{share.token}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_title"] == "Backend"
    assert body["client_name"] == "Acme"
    assert [c["full_name"] for c in body["candidates"]] == ["Grace Hopper"]
    # No contact details leak through the public view.
    assert "email" not in body["candidates"][0]
    assert "phone" not in body["candidates"][0]


def test_public_share_unknown_token_404(client_with_db):
    assert client_with_db.get("/share/does-not-exist").status_code == 404


def test_public_share_expired_token_404(client_with_db, db_session):
    past = datetime.now(timezone.utc) - timedelta(days=1)
    share = _seed_share(db_session, expires_at=past)
    assert client_with_db.get(f"/share/{share.token}").status_code == 404


def test_public_share_after_revoke_404(client_with_db_and_auth, db_session):
    share = _seed_share(db_session)
    # Revoke through the authed endpoint, then the public view is gone.
    assert client_with_db_and_auth.delete(f"/shares/{share.id}").status_code == 204
    assert client_with_db_and_auth.get(f"/share/{share.token}").status_code == 404
