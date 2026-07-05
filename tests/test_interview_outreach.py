"""Unit + API tests for Phase 10 interview flags and stage-aware outreach."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from interview_flags import summarize_notes
from outreach import draft_outreach


# ── Unit: interview flags ────────────────────────────────────────────────────

def test_summary_splits_green_and_red():
    notes = (
        "Confident and articulate on system design. "
        "Struggled to explain testing. Answers on conflict were vague."
    )
    s = summarize_notes(notes)
    assert len(s.green_flags) == 1
    assert len(s.red_flags) == 2
    assert s.recommended_step


def test_summary_all_positive_advances():
    s = summarize_notes("Excellent and impressive throughout. Very strong.")
    assert s.red_flags == []
    assert "advance" in s.recommended_step.lower()


def test_summary_empty_gives_guidance():
    assert summarize_notes("").recommended_step


# ── Unit: stage-aware outreach ───────────────────────────────────────────────

def test_stage_drafts_differ():
    assert "won't be moving forward" in draft_outreach("Ada", stage="rejection").body
    assert "offer" in draft_outreach("Ada", stage="offer").body.lower()
    assert "invite you to interview" in draft_outreach("Ada", stage="interview").body
    # Unknown stage → first-touch fallback.
    assert "reach out" in draft_outreach("Ada", stage="nope").body.lower()


# ── API: interview flags ─────────────────────────────────────────────────────

def test_interview_flags_endpoint(client_with_db_and_auth):
    r = client_with_db_and_auth.post(
        "/interview/flags",
        json={"notes": "Strong and clear communicator. But struggled on testing."},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["green_flags"]) == 1
    assert len(body["red_flags"]) == 1
    assert body["recommended_step"]


def test_interview_flags_requires_notes(client_with_db_and_auth):
    assert client_with_db_and_auth.post("/interview/flags", json={"notes": ""}).status_code == 422


def test_interview_flags_requires_auth(client_with_db):
    r = client_with_db.post("/interview/flags", json={"notes": "hi"})
    assert r.status_code in (401, 403, 503)


# ── API: stage-aware draft ───────────────────────────────────────────────────

def test_draft_endpoint_honours_stage(client_with_db_and_auth):
    cand = client_with_db_and_auth.post(
        "/candidates", json={"full_name": "Grace Hopper"}
    ).json()
    r = client_with_db_and_auth.post(
        f"/candidates/{cand['id']}/outreach/draft?stage=rejection"
    )
    assert r.status_code == 200
    assert "won't be moving forward" in r.json()["body"]
