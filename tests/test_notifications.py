"""API + unit tests for Phase 6 notifications and outreach."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID, TEST_USER_ID
from db_models import Candidate, Scan
from outreach import draft_outreach


# ── Unit: draft ──────────────────────────────────────────────────────────────

def test_draft_uses_first_name_and_headline():
    d = draft_outreach("Ada Lovelace", headline="Data Engineer", job_title="Lead")
    assert d.body.startswith("Hi Ada,")
    assert d.subject == "Lead opportunity"
    assert "data engineer" in d.body.lower()


def test_draft_handles_empty_name():
    assert draft_outreach("").body.startswith("Hi there,")


# ── High-risk auto-notification ──────────────────────────────────────────────

def _red_scan(db, user=TEST_USER_ID):
    s = Scan(
        user_id=user,
        filename="danger.pdf",
        risk_level="RED",
        risk_score=95,
        prompt_injection_findings=[{"pattern_id": "x", "matched_text": "y", "context": "z"}],
        pii_findings=[],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.0,
        safe_copy_text="x",
        summary="danger",
        match_analysis={},
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


def test_high_risk_candidate_creates_notification(client_with_db_and_auth, db_session):
    red = _red_scan(db_session)
    client_with_db_and_auth.post("/candidates", json={"scan_id": str(red.id)})
    notifs = client_with_db_and_auth.get("/notifications").json()
    assert notifs["unread_count"] == 1
    assert notifs["notifications"][0]["type"] == "high_risk"
    assert "High-risk CV" in notifs["notifications"][0]["title"]


def test_green_candidate_creates_no_notification(client_with_db_and_auth):
    client_with_db_and_auth.post("/candidates", json={"full_name": "Safe Person"})
    assert client_with_db_and_auth.get("/notifications").json()["unread_count"] == 0


# ── Notification read flow ───────────────────────────────────────────────────

def test_mark_notification_read(client_with_db_and_auth, db_session):
    red = _red_scan(db_session)
    client_with_db_and_auth.post("/candidates", json={"scan_id": str(red.id)})
    n = client_with_db_and_auth.get("/notifications").json()["notifications"][0]
    assert client_with_db_and_auth.get("/notifications/unread-count").json()["count"] == 1
    r = client_with_db_and_auth.post(f"/notifications/{n['id']}/read")
    assert r.status_code == 200
    assert r.json()["read"] is True
    assert client_with_db_and_auth.get("/notifications/unread-count").json()["count"] == 0


def test_mark_all_read(client_with_db_and_auth, db_session):
    for _ in range(3):
        client_with_db_and_auth.post(
            "/candidates", json={"scan_id": str(_red_scan(db_session).id)}
        )
    assert client_with_db_and_auth.get("/notifications/unread-count").json()["count"] == 3
    client_with_db_and_auth.post("/notifications/read-all")
    assert client_with_db_and_auth.get("/notifications/unread-count").json()["count"] == 0


def test_notifications_are_tenant_scoped(client_with_db_and_auth, db_session):
    from db_models import Notification

    db_session.add(
        Notification(user_id=OTHER_USER_ID, type="info", title="Theirs")
    )
    db_session.commit()
    assert client_with_db_and_auth.get("/notifications").json()["unread_count"] == 0


# ── Outreach ─────────────────────────────────────────────────────────────────

def test_outreach_draft_log_and_list(client_with_db_and_auth):
    cand = client_with_db_and_auth.post(
        "/candidates", json={"full_name": "Grace Hopper", "headline": "Compiler Pioneer"}
    ).json()

    draft = client_with_db_and_auth.post(f"/candidates/{cand['id']}/outreach/draft")
    assert draft.status_code == 200
    assert draft.json()["body"].startswith("Hi Grace,")

    logged = client_with_db_and_auth.post(
        f"/candidates/{cand['id']}/outreach",
        json={"channel": "email", "subject": "Hello", "body": draft.json()["body"]},
    )
    assert logged.status_code == 201

    history = client_with_db_and_auth.get(f"/candidates/{cand['id']}/outreach").json()
    assert len(history) == 1
    assert history[0]["channel"] == "email"


def test_outreach_for_other_tenants_candidate_404(client_with_db_and_auth, db_session):
    other = Candidate(user_id=OTHER_USER_ID, full_name="Theirs", source="manual")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    r = client_with_db_and_auth.post(
        f"/candidates/{other.id}/outreach", json={"body": "hi"}
    )
    assert r.status_code == 404
