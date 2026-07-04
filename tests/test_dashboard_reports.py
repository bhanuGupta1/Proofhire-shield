"""API tests for the Phase 4 dashboard, today queue and reports."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from conftest import OTHER_USER_ID, TEST_USER_ID
from db_models import Candidate, Scan


def _scan(db, user=TEST_USER_ID, risk="GREEN"):
    s = Scan(
        user_id=user,
        filename="cv.pdf",
        risk_level=risk,
        risk_score=90 if risk == "RED" else 5,
        prompt_injection_findings=[],
        pii_findings=[],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.0,
        safe_copy_text="x",
        summary="ok",
        match_analysis={},
    )
    db.add(s)
    db.commit()
    db.refresh(s)
    return s


# ── Dashboard metrics ────────────────────────────────────────────────────────

def test_metrics_counts_by_status_and_risk(client_with_db_and_auth, db_session):
    client_with_db_and_auth.post("/candidates", json={"full_name": "A"})
    c2 = client_with_db_and_auth.post("/candidates", json={"full_name": "B"}).json()
    client_with_db_and_auth.patch(f"/candidates/{c2['id']}", json={"status": "hired"})
    client_with_db_and_auth.post("/jobs", json={"title": "Open Role"})
    # Two scans of differing risk, owned by the caller.
    _scan(db_session, risk="GREEN")
    _scan(db_session, risk="RED")

    r = client_with_db_and_auth.get("/dashboard/metrics")
    assert r.status_code == 200, r.text
    m = r.json()
    assert m["candidates_total"] == 2
    assert m["candidates_by_status"]["new"] == 1
    assert m["candidates_by_status"]["hired"] == 1
    assert m["jobs_total"] == 1
    assert m["open_jobs"] == 1
    assert m["risk"]["GREEN"] == 1
    assert m["risk"]["RED"] == 1


def test_metrics_are_tenant_scoped(client_with_db_and_auth, db_session):
    # Another user's candidate must not leak into the caller's totals.
    db_session.add(
        Candidate(user_id=OTHER_USER_ID, full_name="Theirs", source="manual")
    )
    db_session.commit()
    m = client_with_db_and_auth.get("/dashboard/metrics").json()
    assert m["candidates_total"] == 0


# ── Today ────────────────────────────────────────────────────────────────────

def test_today_surfaces_new_high_risk_and_empty_jobs(
    client_with_db_and_auth, db_session
):
    # A new candidate (status defaults to 'new').
    client_with_db_and_auth.post("/candidates", json={"full_name": "Fresh"})
    # A high-risk candidate promoted from a RED scan.
    red = _scan(db_session, risk="RED")
    client_with_db_and_auth.post("/candidates", json={"scan_id": str(red.id)})
    # An open job with nobody placed.
    client_with_db_and_auth.post("/jobs", json={"title": "Empty Job"})

    t = client_with_db_and_auth.get("/today").json()
    assert t["new_candidates_count"] == 2  # both new
    assert t["high_risk_count"] == 1
    assert t["high_risk_candidates"][0]["risk_level"] == "RED"
    assert t["open_jobs_without_candidates_count"] == 1
    assert t["open_jobs_without_candidates"][0]["title"] == "Empty Job"


def test_today_empty_job_disappears_once_candidate_placed(client_with_db_and_auth):
    job = client_with_db_and_auth.post("/jobs", json={"title": "J"}).json()
    cand = client_with_db_and_auth.post("/candidates", json={"full_name": "C"}).json()
    before = client_with_db_and_auth.get("/today").json()
    assert before["open_jobs_without_candidates_count"] == 1
    client_with_db_and_auth.post(
        f"/jobs/{job['id']}/placements", json={"candidate_id": cand["id"]}
    )
    after = client_with_db_and_auth.get("/today").json()
    assert after["open_jobs_without_candidates_count"] == 0


# ── Reports ──────────────────────────────────────────────────────────────────

def test_report_lists_shortlisted_candidates(client_with_db_and_auth):
    job = client_with_db_and_auth.post(
        "/jobs", json={"title": "Backend", "client_name": "Acme"}
    ).json()
    cand = client_with_db_and_auth.post("/candidates", json={"full_name": "Grace"}).json()
    client_with_db_and_auth.post(
        f"/jobs/{job['id']}/shortlist", json={"candidate_id": cand["id"]}
    )
    r = client_with_db_and_auth.get(f"/jobs/{job['id']}/report")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["job_title"] == "Backend"
    assert body["client_name"] == "Acme"
    assert [c["full_name"] for c in body["candidates"]] == ["Grace"]


def test_report_pdf_is_generated(client_with_db_and_auth):
    job = client_with_db_and_auth.post("/jobs", json={"title": "Role"}).json()
    cand = client_with_db_and_auth.post("/candidates", json={"full_name": "Ada"}).json()
    client_with_db_and_auth.post(
        f"/jobs/{job['id']}/shortlist", json={"candidate_id": cand["id"]}
    )
    r = client_with_db_and_auth.get(f"/jobs/{job['id']}/report.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_report_cross_tenant_is_404(client_with_db_and_auth, db_session):
    from db_models import Job

    other = Job(user_id=OTHER_USER_ID, title="Theirs")
    db_session.add(other)
    db_session.commit()
    db_session.refresh(other)
    assert client_with_db_and_auth.get(f"/jobs/{other.id}/report").status_code == 404


def test_dashboard_requires_auth(client_with_db):
    assert client_with_db.get("/dashboard/metrics").status_code in (401, 403, 503)
