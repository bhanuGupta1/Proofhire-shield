"""Unit + API tests for Phase 3 matching (matching.py + routers/matching.py)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID
from db_models import Candidate, Scan
from matching import (
    candidate_skills,
    score_candidate_for_job,
    talent_search_score,
)


# ── Unit: pure scoring ───────────────────────────────────────────────────────

def test_candidate_skills_flattens_and_normalizes():
    ma = {"skills": {"lang": ["Python", "Go"], "web": ["React.js"]}}
    assert candidate_skills(ma) == {"python", "go", "react.js"}


def test_candidate_skills_empty_when_no_analysis():
    assert candidate_skills(None) == set()
    assert candidate_skills({}) == set()


def test_score_partial_and_subword_match():
    cs = {"python", "react.js", "postgresql"}
    r = score_candidate_for_job(["python", "react", "kubernetes"], cs)
    assert r.matched_skills == ["python", "react"]  # react ⊂ react.js
    assert r.missing_skills == ["kubernetes"]
    assert abs(r.score - 2 / 3) < 1e-9


def test_score_zero_when_no_required_skills():
    assert score_candidate_for_job([], {"python"}).score == 0.0


def test_go_does_not_falsely_match_golang():
    # Substring safety: 'go' must not match 'golang' (word-part matching only).
    r = score_candidate_for_job(["go"], {"golang"})
    assert r.matched_skills == []


def test_talent_search_fraction_of_terms():
    cs = {"python"}
    # 'python' hits skills, 'engineer' misses → 1/2.
    assert abs(talent_search_score("python engineer", cs, None, "Ada") - 0.5) < 1e-9
    # Fully covered by headline.
    assert talent_search_score("backend dev", cs, "Backend dev", "Ada") == 1.0


# ── API: auto-match ──────────────────────────────────────────────────────────

def _scan_with_skills(db, skills_map, user):
    scan = Scan(
        user_id=user,
        filename="cv.pdf",
        risk_level="GREEN",
        risk_score=5,
        prompt_injection_findings=[],
        pii_findings=[],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.0,
        safe_copy_text="x",
        summary="ok",
        match_analysis={"skills": skills_map},
    )
    db.add(scan)
    db.commit()
    db.refresh(scan)
    return scan


def test_auto_match_ranks_by_skill_overlap(client_with_db_and_auth, db_session):
    from conftest import TEST_USER_ID

    job = client_with_db_and_auth.post(
        "/jobs",
        json={"title": "Backend", "required_skills": ["python", "postgres", "aws"]},
    ).json()

    strong = _scan_with_skills(
        db_session, {"a": ["Python", "Postgres", "AWS"]}, TEST_USER_ID
    )
    weak = _scan_with_skills(db_session, {"a": ["Python"]}, TEST_USER_ID)
    db_session.add(
        Candidate(user_id=TEST_USER_ID, full_name="Strong Fit", scan_id=strong.id)
    )
    db_session.add(
        Candidate(user_id=TEST_USER_ID, full_name="Weak Fit", scan_id=weak.id)
    )
    db_session.add(
        Candidate(user_id=TEST_USER_ID, full_name="No Skills", source="manual")
    )
    db_session.commit()

    r = client_with_db_and_auth.post(f"/jobs/{job['id']}/auto-match")
    assert r.status_code == 200, r.text
    body = r.json()
    names = [m["full_name"] for m in body["matches"]]
    # No-skills candidate excluded; strong ranked above weak.
    assert names == ["Strong Fit", "Weak Fit"]
    assert body["matches"][0]["score"] == 100
    assert body["matches"][0]["missing_skills"] == []
    assert body["matches"][1]["missing_skills"] == ["postgres", "aws"]


def test_auto_match_cross_tenant_job_404(client_with_db_and_auth, db_session):
    from db_models import Job

    other = Job(user_id=OTHER_USER_ID, title="Theirs", required_skills=["python"])
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    r = client_with_db_and_auth.post(f"/jobs/{other.id}/auto-match")
    assert r.status_code == 404


def test_auto_match_requires_auth(client_with_db):
    # Needs a real job id shape; unauth rejected before lookup anyway.
    import uuid as _uuid

    r = client_with_db.post(f"/jobs/{_uuid.uuid4()}/auto-match")
    assert r.status_code in (401, 403, 503)


# ── API: talent search ───────────────────────────────────────────────────────

def test_talent_search_ranks_and_filters(client_with_db_and_auth, db_session):
    from conftest import TEST_USER_ID

    s = _scan_with_skills(db_session, {"a": ["Python", "Django"]}, TEST_USER_ID)
    db_session.add(
        Candidate(user_id=TEST_USER_ID, full_name="Pythonista", scan_id=s.id)
    )
    db_session.add(
        Candidate(
            user_id=TEST_USER_ID,
            full_name="Java Dev",
            headline="Java engineer",
            source="manual",
        )
    )
    db_session.commit()

    r = client_with_db_and_auth.post("/talent/search", json={"query": "python django"})
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert [h["full_name"] for h in results] == ["Pythonista"]
    assert results[0]["score"] == 100


def test_talent_search_only_returns_own_candidates(
    client_with_db_and_auth, db_session
):
    s = _scan_with_skills(db_session, {"a": ["Python"]}, OTHER_USER_ID)
    db_session.add(
        Candidate(user_id=OTHER_USER_ID, full_name="Theirs", scan_id=s.id)
    )
    db_session.commit()
    r = client_with_db_and_auth.post("/talent/search", json={"query": "python"})
    assert r.json()["results"] == []
