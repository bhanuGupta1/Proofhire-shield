"""API tests for the candidates router (platform Phase 1)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID, TEST_ORG_ID, TEST_USER_ID
from db_models import Scan


def _make_scan(db_session, **overrides):
    scan = Scan(
        user_id=overrides.get("user_id", TEST_USER_ID),
        org_id=overrides.get("org_id"),
        filename=overrides.get("filename", "ada_lovelace.pdf"),
        risk_level=overrides.get("risk_level", "GREEN"),
        risk_score=overrides.get("risk_score", 5),
        prompt_injection_findings=[],
        pii_findings=overrides.get(
            "pii_findings",
            [
                {"pii_type": "email", "matched_text": "ada@example.com"},
                {"pii_type": "phone", "matched_text": "+64 21 000 000"},
            ],
        ),
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.1,
        safe_copy_text="cleaned",
        summary="ok",
        match_analysis=overrides.get(
            "match_analysis",
            {"experience_tier": "Senior", "years_experience": 8},
        ),
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    return scan


# ── Create ───────────────────────────────────────────────────────────────────

def test_create_manual_candidate(client_with_db_and_auth):
    r = client_with_db_and_auth.post(
        "/candidates", json={"full_name": "Grace Hopper", "tags": ["cobol"]}
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["full_name"] == "Grace Hopper"
    assert body["source"] == "manual"
    assert body["status"] == "new"
    assert body["tags"] == ["cobol"]
    assert body["scan_id"] is None


def test_create_requires_name_when_no_scan(client_with_db_and_auth):
    r = client_with_db_and_auth.post("/candidates", json={})
    assert r.status_code == 422


def test_promote_from_scan_copies_extracted_fields(
    client_with_db_and_auth, db_session
):
    scan = _make_scan(db_session)
    r = client_with_db_and_auth.post("/candidates", json={"scan_id": str(scan.id)})
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["source"] == "scan"
    assert body["scan_id"] == str(scan.id)
    # Contact details lifted from the scan's PII findings.
    assert body["email"] == "ada@example.com"
    assert body["phone"] == "+64 21 000 000"
    # Headline synthesised from match analysis.
    assert body["headline"] == "Senior · 8 yrs experience"
    # Name defaulted from the filename stem (recruiter edits later).
    assert body["full_name"] == "ada_lovelace"
    # Risk badge denormalised from the linked scan.
    assert body["risk_level"] == "GREEN"


def test_promote_from_other_users_scan_is_404(client_with_db_and_auth, db_session):
    scan = _make_scan(db_session, user_id=OTHER_USER_ID)
    r = client_with_db_and_auth.post("/candidates", json={"scan_id": str(scan.id)})
    assert r.status_code == 404


def test_create_requires_auth(client_with_db):
    # No auth override + Clerk unconfigured in tests → get_current_user rejects
    # with 503 ("auth not configured"); a deployed instance with Clerk set
    # returns 401 for a missing/invalid token. Either way: never created.
    r = client_with_db.post("/candidates", json={"full_name": "X"})
    assert r.status_code in (401, 403, 503)


# ── List / detail / tenant isolation ─────────────────────────────────────────

def test_list_returns_only_callers_candidates(client_with_db_and_auth):
    client_with_db_and_auth.post("/candidates", json={"full_name": "Mine"})
    r = client_with_db_and_auth.get("/candidates")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["candidates"][0]["full_name"] == "Mine"


def test_list_search_and_status_filter(client_with_db_and_auth):
    client_with_db_and_auth.post("/candidates", json={"full_name": "Alan Turing"})
    client_with_db_and_auth.post("/candidates", json={"full_name": "Ada Lovelace"})
    r = client_with_db_and_auth.get("/candidates", params={"q": "turing"})
    assert r.json()["count"] == 1
    assert r.json()["candidates"][0]["full_name"] == "Alan Turing"


def test_detail_cross_tenant_is_404(client_with_db_and_auth, db_session):
    from db_models import Candidate

    other = Candidate(user_id=OTHER_USER_ID, full_name="Not Yours", source="manual")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    r = client_with_db_and_auth.get(f"/candidates/{other.id}")
    assert r.status_code == 404


# ── Update / delete ──────────────────────────────────────────────────────────

def test_update_candidate_status_and_notes(client_with_db_and_auth):
    created = client_with_db_and_auth.post(
        "/candidates", json={"full_name": "Edit Me"}
    ).json()
    r = client_with_db_and_auth.patch(
        f"/candidates/{created['id']}",
        json={"status": "shortlisted", "notes": "great fit"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "shortlisted"
    assert r.json()["notes"] == "great fit"


def test_delete_candidate(client_with_db_and_auth):
    created = client_with_db_and_auth.post(
        "/candidates", json={"full_name": "Delete Me"}
    ).json()
    r = client_with_db_and_auth.delete(f"/candidates/{created['id']}")
    assert r.status_code == 204
    assert client_with_db_and_auth.get(f"/candidates/{created['id']}").status_code == 404


# ── Org sharing ──────────────────────────────────────────────────────────────

def test_org_member_sees_org_candidate(client_with_db_auth_and_org, db_session):
    from db_models import Candidate

    shared = Candidate(
        user_id=OTHER_USER_ID,
        org_id=TEST_ORG_ID,
        full_name="Org Shared",
        source="manual",
    )
    db_session.add(shared)
    db_session.commit()
    r = client_with_db_auth_and_org.get("/candidates")
    assert r.status_code == 200
    names = [c["full_name"] for c in r.json()["candidates"]]
    assert "Org Shared" in names
