"""
HTTP-layer tests via FastAPI TestClient.

These verify that upload guards, error mappings, and response shapes
work correctly end-to-end through the full request/response cycle —
not just at the Python-function level.
"""
import sys, os, io
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi.testclient import TestClient
from pathlib import Path

# Ensure backend is importable before importing main
from main import app

client = TestClient(app, raise_server_exceptions=False)

DEMO_DIR = Path(__file__).parent.parent / "demo-cvs"


def _post_file(path: Path | None = None, *,
               content: bytes | None = None,
               filename: str = "cv.pdf",
               content_type: str = "application/pdf",
               endpoint: str = "/scan-cv"):
    if path:
        content = path.read_bytes()
    return client.post(
        endpoint,
        files={"file": (filename, io.BytesIO(content), content_type)},
    )


# ── Health check ─────────────────────────────────────────────────────────────

def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


# ── Content-type guard (F-09) ─────────────────────────────────────────────────

def test_unsupported_content_type_rejected():
    r = _post_file(content=b"data", filename="cv.csv", content_type="text/csv")
    assert r.status_code == 415


def test_allowed_content_types_accepted():
    # Plain text — should reach the scanner (may 422 if no text, that's fine)
    r = _post_file(content=b"Sarah Chen, Engineer.", filename="cv.txt",
                   content_type="text/plain")
    assert r.status_code in (200, 422)


# ── Magic-bytes guard (400 = declared type != content; 422 = unparseable) ─────

def test_fake_pdf_content_type_returns_400():
    """Binary garbage claiming to be PDF → 400 (declared type != content)."""
    r = _post_file(content=b"This is not a PDF at all",
                   filename="evil.pdf", content_type="application/pdf")
    assert r.status_code == 400
    assert r.json()["detail"]  # error message present


def test_fake_docx_content_type_returns_400():
    r = _post_file(
        content=b"Not a DOCX either",
        filename="evil.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert r.status_code == 400


def test_corrupt_pdf_with_valid_magic_returns_422():
    """Correct %PDF magic but unparseable body → 422, not 400."""
    r = _post_file(content=b"%PDF-1.4\nnot really a pdf body",
                   filename="cv.pdf", content_type="application/pdf")
    assert r.status_code == 422


def test_filename_path_traversal_is_sanitised():
    r = _post_file(DEMO_DIR / "01_clean.pdf", filename="../../etc/cv.pdf")
    assert r.status_code == 200
    name = r.json()["result"]["filename"]
    assert "/" not in name and "\\" not in name and ".." not in name


def test_binary_content_as_txt_extension_rejected():
    # PDF/DOCX bytes mislabelled .txt would be decoded as raw text, leaving hidden
    # layers unscanned — reject the extension/content mismatch with 400.
    r = _post_file(content=b"%PDF-1.5\n1 0 obj", filename="cv.txt", content_type="text/plain")
    assert r.status_code == 400
    r2 = _post_file(content=b"PK\x03\x04\x14\x00", filename="cv.txt", content_type="text/plain")
    assert r2.status_code == 400


# ── Size limit (F-10) ─────────────────────────────────────────────────────────

def test_oversized_upload_rejected_by_middleware():
    # Simulate Content-Length header for a 12 MB upload (over 10 MB cap).
    # TestClient sends Content-Length; middleware should reject before body is read.
    large = b"A" * (11 * 1024 * 1024)
    r = client.post(
        "/scan-cv",
        content=large,
        headers={
            "Content-Type": "multipart/form-data; boundary=boundary",
            "Content-Length": str(len(large)),
        },
    )
    assert r.status_code == 413


# ── Successful scan of demo CVs ───────────────────────────────────────────────

def test_clean_cv_scan_returns_green():
    r = _post_file(DEMO_DIR / "01_clean.pdf")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["risk_level"] == "GREEN"


def test_injection_cv_scan_returns_red():
    r = _post_file(DEMO_DIR / "02_prompt_injection.pdf")
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["result"]["risk_level"] == "RED"
    assert len(body["result"]["prompt_injection_findings"]) > 0


def test_pii_heavy_cv_scan_not_green():
    r = _post_file(DEMO_DIR / "04_pii_heavy.pdf")
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["risk_level"] != "GREEN"


# ── Response shape ────────────────────────────────────────────────────────────

def test_scan_response_has_required_fields():
    r = _post_file(DEMO_DIR / "01_clean.pdf")
    result = r.json()["result"]
    required = {
        "filename", "risk_level", "risk_score",
        "prompt_injection_findings", "pii_findings",
        "ai_text_likelihood", "ai_text_score",
        "original_text", "safe_copy_text", "summary",
    }
    assert required.issubset(result.keys())


def test_risk_score_in_range():
    r = _post_file(DEMO_DIR / "01_clean.pdf")
    score = r.json()["result"]["risk_score"]
    assert 0 <= score <= 100


def test_ai_likelihood_is_valid_enum():
    r = _post_file(DEMO_DIR / "05_ai_padded.pdf")
    likelihood = r.json()["result"]["ai_text_likelihood"]
    assert likelihood in ("LIKELY", "POSSIBLE", "UNLIKELY")


# ── Trust report endpoint ─────────────────────────────────────────────────────

def test_trust_report_returns_pdf():
    r = _post_file(DEMO_DIR / "01_clean.pdf", endpoint="/trust-report")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert r.content[:4] == b"%PDF"


def test_trust_report_for_injection_cv():
    r = _post_file(DEMO_DIR / "02_prompt_injection.pdf", endpoint="/trust-report")
    assert r.status_code == 200
    assert r.content[:4] == b"%PDF"


def test_trust_report_bad_file_returns_400():
    r = _post_file(content=b"garbage", filename="bad.pdf",
                   content_type="application/pdf", endpoint="/trust-report")
    assert r.status_code == 400


# ── Match analysis via /scan-cv (D1) ─────────────────────────────────────────

def test_match_analysis_no_skills():
    r = _post_file(content=b"Sarah is a thoughtful candidate seeking work in a kind organisation.",
                   filename="cv.txt", content_type="text/plain")
    assert r.status_code == 200
    m = r.json()["result"]["match_analysis"]
    assert m["total_skills_found"] == 0
    assert m["experience_tier"] == "Entry"


def test_match_analysis_senior_cv():
    text = "Senior Engineer at Xero. 8 years experience. Python, AWS, Docker."
    r = _post_file(content=text.encode(), filename="cv.txt", content_type="text/plain")
    assert r.status_code == 200
    m = r.json()["result"]["match_analysis"]
    assert m["experience_tier"] == "Senior"
    assert m["years_experience"] == 8


def test_completeness_full_cv_via_api():
    text = (
        "Sarah Chen — Senior Software Engineer\n"
        "sarah.chen@example.com | +64 21 555 0101 | linkedin.com/in/sarahc | github.com/sarahc\n"
        "Xero (2020 - present) — Senior Engineer\n"
        "Built billing API, reduced p99 latency 420ms->95ms.\n"
        "Skills: Python, Django, FastAPI, PostgreSQL, AWS, Docker, Kubernetes, Redis.\n"
        + ("word " * 320)
    )
    r = _post_file(content=text.encode(), filename="cv.txt", content_type="text/plain")
    assert r.status_code == 200
    m = r.json()["result"]["match_analysis"]
    assert m["completeness"]["score"] >= 70


def test_red_flags_broad_stack_via_api():
    text = (
        "1 year of experience. Skills: Python, JavaScript, TypeScript, Java, C#, Go, "
        "Rust, Ruby, PHP, Swift, Kotlin, Scala, R, SQL, React, Vue, Angular, Django."
    )
    r = _post_file(content=text.encode(), filename="cv.txt", content_type="text/plain")
    assert r.status_code == 200
    m = r.json()["result"]["match_analysis"]
    assert any("broad tech stack" in f.lower() for f in m["red_flags"])


def test_candidate_summary_nonempty_via_api():
    r = _post_file(DEMO_DIR / "01_clean.pdf")
    assert r.status_code == 200
    m = r.json()["result"]["match_analysis"]
    assert isinstance(m["summary"], str)
    assert m["summary"]


# ── /match-jd endpoint ───────────────────────────────────────────────────────

def test_match_jd_endpoint_returns_score():
    """Phase 9 — a one-skill JD is sparse, score capped at 60 with a note."""
    r = client.post("/match-jd", json={"cv_text": "Python, AWS, Docker.", "jd_text": "Need Python."})
    assert r.status_code == 200
    body = r.json()
    assert body["match_score"] <= 60
    assert "Python" in body["matched_skills"]
    assert body["coverage_note"]  # explains the cap


def test_match_jd_endpoint_returns_full_score_with_dense_jd():
    """A JD with 3+ skills is statistically informative; no cap, no note."""
    r = client.post(
        "/match-jd",
        json={
            "cv_text": "Python, AWS, Docker, PostgreSQL.",
            "jd_text": "We need Python, AWS, and PostgreSQL.",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["match_score"] > 60
    assert body["coverage_note"] == ""


def test_match_jd_empty_text_rejected():
    r = client.post("/match-jd", json={"cv_text": "", "jd_text": "Need Python."})
    assert r.status_code == 422


def test_match_jd_oversized_text_rejected():
    big = "x" * 20001
    r = client.post("/match-jd", json={"cv_text": big, "jd_text": "Need Python."})
    assert r.status_code == 422


# ── /assessment endpoint (Phase 2) ───────────────────────────────────────────

def _assessment_body():
    """After the Phase-2 review fix, the endpoint accepts only cv_text + role_context;
    structured signals are derived server-side."""
    return {
        "cv_text": "Sarah Chen, Senior Engineer. 8 years experience. Python, AWS.",
        "role_context": "Senior backend engineer at a fintech.",
    }


def test_assessment_endpoint_503_without_api_key(client_with_auth_only, monkeypatch):
    """503 detail must not disclose whether EITHER API key is configured.
    Phase 7.7: auth is now required, so we use the auth fixture; no DB means
    the Pro gate degrades open and the keyless 503 path is what we hit."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = client_with_auth_only.post("/assessment", json=_assessment_body())
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "ANTHROPIC_API_KEY" not in detail
    assert "GROQ_API_KEY" not in detail
    assert "temporarily unavailable" in detail.lower()


def test_assessment_endpoint_happy_path(client_with_auth_only, monkeypatch):
    """Pre-Phase-7 happy path: with auth + no DB (gate degrades open) +
    monkeypatched report generator, /assessment returns 200."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME

    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="Senior Python engineer",
        dimensions=[AssessmentDimension(name="X", text="Y")],
        overall_recommendation="Worth interviewing",
        overall_score=78,
        next_steps=["schedule interview", "verify AWS", "check refs"],
    )
    import main as main_module

    monkeypatch.setattr(main_module, "generate_assessment_report", lambda **kw: canned)

    r = client_with_auth_only.post("/assessment", json=_assessment_body())
    assert r.status_code == 200
    body = r.json()
    assert body["framework"] == FRAMEWORK_NAME
    assert body["overall_score"] == 78
    assert len(body["next_steps"]) == 3


def test_assessment_endpoint_validates_required_fields(client_with_auth_only):
    # Missing cv_text -> 422.
    r = client_with_auth_only.post("/assessment", json={"role_context": "x"})
    assert r.status_code == 422


def test_assessment_endpoint_oversized_cv_text_rejected(client_with_auth_only):
    body = _assessment_body()
    body["cv_text"] = "x" * 20001
    r = client_with_auth_only.post("/assessment", json=body)
    assert r.status_code == 422


# ── Phase 3: /scan-cv persistence + scan_id ──────────────────────────────────

def test_scan_cv_no_scan_id_when_db_unavailable():
    """Without get_db overridden, the default get_db yields None and the response
    contains scan_id=None — the Phase 1/2 stateless behaviour is preserved."""
    r = _post_file(DEMO_DIR / "01_clean.pdf")
    assert r.status_code == 200
    body = r.json()["result"]
    assert body["scan_id"] is None


def test_scan_cv_anonymous_with_db_does_not_persist(client_with_db, db_session):
    """Phase 4: DB available but no authenticated user → still no persistence.
    Nothing reaches the table without a known owner."""
    from db_models import Scan

    r = client_with_db.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()["result"]
    assert body["scan_id"] is None
    assert db_session.query(Scan).count() == 0


def test_scan_cv_returns_scan_id_when_db_and_auth(client_with_db_and_auth):
    r = client_with_db_and_auth.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()["result"]
    assert body["scan_id"] is not None
    import uuid as _uuid

    parsed = _uuid.UUID(body["scan_id"])
    assert str(parsed) == body["scan_id"]


def test_scan_cv_persists_with_user_id_when_authed(client_with_db_and_auth, db_session):
    """Privacy + Phase 4: the persisted row stores safe_copy_text only AND tags
    it with the authenticated Clerk user_id."""
    from db_models import Scan
    from conftest import TEST_USER_ID

    r = client_with_db_and_auth.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    rows = db_session.query(Scan).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.filename == "01_clean.pdf"
    assert row.safe_copy_text  # non-empty
    assert row.user_id == TEST_USER_ID
    assert "original_text" not in {c.name for c in Scan.__table__.columns}


def test_scan_cv_response_scan_id_matches_db_row(client_with_db_and_auth, db_session):
    from db_models import Scan

    r = client_with_db_and_auth.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    body_scan_id = r.json()["result"]["scan_id"]
    rows = db_session.query(Scan).all()
    assert len(rows) == 1
    assert str(rows[0].id) == body_scan_id


# ── Phase 3: /assessment with scan_id input + persistence ────────────────────

def _make_persisted_scan_for_user(db_session, user_id):
    from db_models import Scan

    scan = Scan(
        user_id=user_id,
        filename="cv.pdf",
        risk_level="GREEN",
        risk_score=0,
        prompt_injection_findings=[],
        pii_findings=[],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.0,
        safe_copy_text="Sarah Chen, Senior Engineer. Python, AWS.",
        summary="No issues detected.",
        match_analysis={"experience_tier": "Senior", "summary": "x"},
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    return scan


def test_assessment_with_scan_id_loads_and_persists(client_with_db_and_auth, db_session, monkeypatch):
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    from conftest import TEST_USER_ID
    from db_models import Assessment
    import main as main_module

    # Phase 7.3: /assessment is now Pro-gated for signed-in callers. This test
    # exercises the post-gate persistence flow, so make the test user Pro.
    _make_user_pro(db_session, TEST_USER_ID)
    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)

    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="Senior Python engineer",
        dimensions=[AssessmentDimension(name="Profile", text="Y")],
        overall_recommendation="Worth interviewing",
        overall_score=80,
        next_steps=["schedule interview", "verify AWS", "check refs"],
        provider_used="anthropic",
    )
    monkeypatch.setattr(main_module, "generate_assessment_report", lambda **kw: canned)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={"scan_id": str(scan.id), "role_context": "Backend at fintech."},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["overall_score"] == 80
    assert body["framework"] == FRAMEWORK_NAME

    rows = db_session.query(Assessment).all()
    assert len(rows) == 1
    assert str(rows[0].scan_id) == str(scan.id)
    assert rows[0].user_id == TEST_USER_ID
    assert rows[0].provider_used == "anthropic"
    assert rows[0].overall_score == 80


def test_assessment_anonymous_returns_401_or_503():
    """Phase 7.7: /assessment now requires auth for ALL inputs. Anonymous calls
    return 401 in prod (Clerk configured) or 503 in test env (not configured),
    matching the /scans pattern. No body leakage either way."""
    r = client.post(
        "/assessment",
        json={"scan_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code in (401, 503)
    r2 = client.post(
        "/assessment",
        json={"cv_text": "Sarah Chen, Senior Engineer."},
    )
    assert r2.status_code in (401, 503)


def test_assessment_with_auth_no_db_returns_503(client_with_auth_only):
    """Authenticated but no DB configured → 503 (can't honour scan_id)."""
    r = client_with_auth_only.post(
        "/assessment",
        json={"scan_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 503


def test_assessment_with_unknown_scan_id_returns_404(client_with_db_and_auth, db_session):
    # Phase 7.3: caller must be Pro to reach the post-gate 404 branch.
    from conftest import TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={"scan_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 404


def test_assessment_other_users_scan_id_returns_404(client_with_db_and_auth, db_session):
    """Security: a known scan_id belonging to a DIFFERENT user must return 404,
    not 200 — never leak that a scan exists or expose its contents."""
    from conftest import OTHER_USER_ID, TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    scan = _make_persisted_scan_for_user(db_session, OTHER_USER_ID)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={"scan_id": str(scan.id)},
    )
    assert r.status_code == 404


# ── Phase 4.3: GET /scans history endpoint ───────────────────────────────────

def test_scans_anonymous_denied():
    """Anonymous → 401 in prod (CLERK_ configured) or 503 in test env (not
    configured). Either way, no body leaks."""
    r = client.get("/scans")
    assert r.status_code in (401, 503)


def test_scans_returns_503_when_no_db(client_with_auth_only):
    r = client_with_auth_only.get("/scans")
    assert r.status_code == 503


def test_scans_empty_when_user_has_no_scans(client_with_db_and_auth):
    r = client_with_db_and_auth.get("/scans")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 0
    assert body["scans"] == []


def test_scans_returns_only_caller_own_scans(client_with_db_and_auth, db_session):
    """Cross-tenant security: a scan tagged with OTHER_USER_ID must not appear
    in the caller's list."""
    from conftest import OTHER_USER_ID, TEST_USER_ID

    own = _make_persisted_scan_for_user(db_session, TEST_USER_ID)
    _make_persisted_scan_for_user(db_session, OTHER_USER_ID)

    r = client_with_db_and_auth.get("/scans")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    assert body["scans"][0]["scan_id"] == str(own.id)
    assert body["scans"][0]["filename"] == "cv.pdf"
    assert body["scans"][0]["risk_level"] == "GREEN"


def test_scans_ordered_newest_first(client_with_db_and_auth, db_session):
    """Newest scan must appear first so the recruiter sees most-recent work."""
    from conftest import TEST_USER_ID

    first = _make_persisted_scan_for_user(db_session, TEST_USER_ID)
    second = _make_persisted_scan_for_user(db_session, TEST_USER_ID)
    # Newer rows have later created_at (server-side default). Verify second
    # appears before first.

    r = client_with_db_and_auth.get("/scans")
    body = r.json()
    assert body["count"] == 2
    ids = [s["scan_id"] for s in body["scans"]]
    assert ids == [str(second.id), str(first.id)]


def test_scans_summary_excludes_safe_copy_text(client_with_db_and_auth, db_session):
    """The list endpoint must NEVER leak safe_copy_text — that's the per-scan
    detail view's job (Phase 4.x / 5)."""
    from conftest import TEST_USER_ID

    _make_persisted_scan_for_user(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.get("/scans")
    body = r.json()
    summary = body["scans"][0]
    assert "safe_copy_text" not in summary
    assert "match_analysis" not in summary
    assert "prompt_injection_findings" not in summary


# ── Phase 5: org-scoped scope on /scans and /assessment ──────────────────────

def _make_persisted_scan_for_user_org(db_session, user_id, org_id):
    from db_models import Scan

    scan = Scan(
        user_id=user_id,
        org_id=org_id,
        filename="cv.pdf",
        risk_level="GREEN",
        risk_score=0,
        prompt_injection_findings=[],
        pii_findings=[],
        ai_text_likelihood="UNLIKELY",
        ai_text_score=0.0,
        safe_copy_text="Sarah Chen, Senior Engineer.",
        summary="No issues detected.",
        match_analysis={"experience_tier": "Senior"},
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    return scan


def test_scan_cv_persists_org_id_when_caller_in_org(client_with_db_auth_and_org, db_session):
    from conftest import TEST_ORG_ID, TEST_USER_ID
    from db_models import Scan

    r = client_with_db_auth_and_org.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    rows = db_session.query(Scan).all()
    assert len(rows) == 1
    assert rows[0].user_id == TEST_USER_ID
    assert rows[0].org_id == TEST_ORG_ID


def test_scans_includes_colleagues_scans_in_same_org(client_with_db_auth_and_org, db_session):
    """A scan created by OTHER_USER_ID but tagged with the caller's TEST_ORG_ID
    must appear in the caller's list — that's the whole point of org sharing."""
    from conftest import OTHER_USER_ID, TEST_ORG_ID, TEST_USER_ID

    own = _make_persisted_scan_for_user_org(db_session, TEST_USER_ID, TEST_ORG_ID)
    colleague = _make_persisted_scan_for_user_org(db_session, OTHER_USER_ID, TEST_ORG_ID)

    r = client_with_db_auth_and_org.get("/scans")
    assert r.status_code == 200
    ids = {s["scan_id"] for s in r.json()["scans"]}
    assert ids == {str(own.id), str(colleague.id)}


def test_scans_excludes_other_orgs_scans(client_with_db_auth_and_org, db_session):
    """A scan tagged with a different org_id must NOT appear, even if the
    creator is a known user in our test data set."""
    from conftest import OTHER_ORG_ID, OTHER_USER_ID, TEST_ORG_ID, TEST_USER_ID

    own = _make_persisted_scan_for_user_org(db_session, TEST_USER_ID, TEST_ORG_ID)
    _make_persisted_scan_for_user_org(db_session, OTHER_USER_ID, OTHER_ORG_ID)

    r = client_with_db_auth_and_org.get("/scans")
    body = r.json()
    assert body["count"] == 1
    assert body["scans"][0]["scan_id"] == str(own.id)


def test_assessment_scan_id_allows_org_member(client_with_db_auth_and_org, db_session, monkeypatch):
    """An admin or viewer in TEST_ORG_ID can assess any scan in that org, even
    one created by a colleague. Caller is Pro (Phase 7.3 generation gate)."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    from conftest import OTHER_USER_ID, TEST_ORG_ID, TEST_USER_ID
    from db_models import Assessment
    import main as main_module

    _make_user_pro(db_session, TEST_USER_ID)
    colleague_scan = _make_persisted_scan_for_user_org(db_session, OTHER_USER_ID, TEST_ORG_ID)

    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="x",
        dimensions=[AssessmentDimension(name="X", text="Y")],
        overall_recommendation="ok",
        overall_score=70,
        next_steps=["a", "b", "c"],
        provider_used="anthropic",
    )
    monkeypatch.setattr(main_module, "generate_assessment_report", lambda **kw: canned)

    r = client_with_db_auth_and_org.post(
        "/assessment",
        json={"scan_id": str(colleague_scan.id)},
    )
    assert r.status_code == 200

    rows = db_session.query(Assessment).all()
    assert len(rows) == 1
    # The Assessment is created BY TEST_USER_ID but INHERITS the scan's org_id.
    assert rows[0].user_id == TEST_USER_ID
    assert rows[0].org_id == TEST_ORG_ID


def test_assessment_scan_id_denies_other_org_scan(client_with_db_auth_and_org, db_session):
    """A scan in a DIFFERENT org returns 404 even to an authed Pro caller —
    org-scope still 404s past the Pro gate."""
    from conftest import OTHER_ORG_ID, OTHER_USER_ID, TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    foreign = _make_persisted_scan_for_user_org(db_session, OTHER_USER_ID, OTHER_ORG_ID)

    r = client_with_db_auth_and_org.post(
        "/assessment",
        json={"scan_id": str(foreign.id)},
    )
    assert r.status_code == 404


def test_assessment_requires_exactly_one_of_cv_text_or_scan_id(client_with_auth_only):
    # Neither → 422.
    r1 = client_with_auth_only.post(
        "/assessment", json={"role_context": "Backend engineer"}
    )
    assert r1.status_code == 422
    # Both → 422 (we don't silently drop cv_text in favour of scan_id).
    r2 = client_with_auth_only.post(
        "/assessment",
        json={
            "cv_text": "Sarah Chen, Senior Engineer.",
            "scan_id": "00000000-0000-0000-0000-000000000000",
        },
    )
    assert r2.status_code == 422


def test_trust_report_does_not_persist_scan_when_db_available(client_with_db, db_session):
    """/trust-report uses scan_cv internally but with persist=False — the PDF
    endpoint must not double-write a scan row that the caller neither asked for
    nor receives the scan_id of."""
    from db_models import Scan

    r = client_with_db.post(
        "/trust-report",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    assert db_session.query(Scan).count() == 0


def test_assessment_with_cv_text_path_does_not_persist(client_with_db_and_auth, db_session, monkeypatch):
    """cv_text-only assessments are intentionally NOT persisted (Phase 3 invariant).
    Phase 7.7: caller must be Pro to reach the path under test."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    from conftest import TEST_USER_ID
    from db_models import Assessment
    import main as main_module

    _make_user_pro(db_session, TEST_USER_ID)

    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="x",
        dimensions=[AssessmentDimension(name="P", text="Q")],
        overall_recommendation="ok",
        overall_score=50,
        next_steps=["a", "b", "c"],
        provider_used="groq",
    )
    monkeypatch.setattr(main_module, "generate_assessment_report", lambda **kw: canned)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={"cv_text": "Sarah Chen, Senior Engineer."},
    )
    assert r.status_code == 200
    rows = db_session.query(Assessment).all()
    assert len(rows) == 0  # explicitly NOT persisted


def test_assessment_endpoint_ignores_client_supplied_trust_claims(
    client_with_auth_only, monkeypatch
):
    """The endpoint must not honour client-supplied match_analysis / risk_signals.
    Pydantic ignores extra fields by default, so smuggling them is silently dropped.
    Phase 7.7: auth required; using client_with_auth_only (no DB → gate degrades open)."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME

    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="Forged",
        dimensions=[AssessmentDimension(name="X", text="Y")],
        overall_recommendation="Worth interviewing",
        overall_score=99,
        next_steps=["a", "b", "c"],
    )
    captured = {}

    def fake_generator(**kwargs):
        captured.update(kwargs)
        return canned

    import main as main_module

    monkeypatch.setattr(main_module, "generate_assessment_report", fake_generator)

    body = {
        "cv_text": "Junior dev, 1 year, no skills.",
        "match_analysis": {"experience_tier": "Principal / Lead", "total_skills_found": 999},
        "risk_signals": {"risk_level": "GREEN", "risk_score": 0, "injection_count": 0, "ai_text_likelihood": "UNLIKELY"},
    }
    r = client_with_auth_only.post("/assessment", json=body)
    assert r.status_code == 200
    # The signals the server actually computed override anything the client sent.
    signals = captured["signals"]
    assert signals["match"]["experience_tier"] != "Principal / Lead"
    assert signals["match"]["total_skills_found"] < 999


# ── Phase 5.3: GET /scans/{scan_id} per-scan detail ──────────────────────────

def _make_full_persisted_scan(db_session, user_id, org_id=None):
    """A scan row with a COMPLETE match_analysis dict so the detail endpoint
    (response_model=ScanResult) can coerce it into MatchAnalysisModel. The
    list-only helpers above use partial dicts because /scans never serialises
    match_analysis; the detail view does."""
    from db_models import Scan

    scan = Scan(
        user_id=user_id,
        org_id=org_id,
        filename="sarah_chen_cv.pdf",
        risk_level="ORANGE",
        risk_score=40,
        prompt_injection_findings=[
            {
                "pattern_id": "ignore_previous",
                "matched_text": "ignore all previous instructions",
                "context": "...ignore all previous instructions and...",
            }
        ],
        pii_findings=[{"pii_type": "EMAIL", "matched_text": "sarah@example.com"}],
        ai_text_likelihood="POSSIBLE",
        ai_text_score=0.5,
        safe_copy_text="Sarah Chen, Senior Engineer. Python, AWS. [hidden instruction blocked]",
        summary="One hidden instruction blocked; one personal data item flagged.",
        match_analysis={
            "skills": {"languages": ["Python"], "cloud": ["AWS"]},
            "experience_tier": "Senior",
            "years_experience": 8,
            "education_level": "Bachelor's",
            "interview_probes": ["Probe AWS scaling decisions"],
            "key_claims": ["Led cloud migration"],
            "total_skills_found": 2,
            "summary": "Senior engineer, cloud-focused.",
            "completeness": {"score": 90, "breakdown": {"contact": True, "skills": True}},
            "red_flags": [],
        },
    )
    db_session.add(scan)
    db_session.commit()
    db_session.refresh(scan)
    return scan


def test_get_scan_anonymous_denied():
    """Anonymous → 401 in prod (CLERK_ configured) or 503 in test env (not
    configured). Either way, no body leaks."""
    r = client.get("/scans/00000000-0000-0000-0000-000000000000")
    assert r.status_code in (401, 503)


def test_get_scan_returns_503_when_no_db(client_with_auth_only):
    r = client_with_auth_only.get("/scans/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 503


def test_get_scan_unknown_id_returns_404(client_with_db_and_auth):
    r = client_with_db_and_auth.get("/scans/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404


def test_get_scan_invalid_uuid_returns_422(client_with_db_and_auth):
    """Path param is typed uuid.UUID — a non-UUID string is rejected by FastAPI
    before the handler runs, so a malformed id never reaches the query."""
    r = client_with_db_and_auth.get("/scans/not-a-uuid")
    assert r.status_code == 422


def test_get_scan_own_scan_returns_full_detail(client_with_db_and_auth, db_session):
    from conftest import TEST_USER_ID

    scan = _make_full_persisted_scan(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.get(f"/scans/{scan.id}")
    assert r.status_code == 200
    body = r.json()
    assert body["scan_id"] == str(scan.id)
    assert body["filename"] == "sarah_chen_cv.pdf"
    assert body["risk_level"] == "ORANGE"
    assert body["risk_score"] == 40
    # Risk evidence rehydrates: stored findings come back intact.
    assert len(body["prompt_injection_findings"]) == 1
    assert body["prompt_injection_findings"][0]["pattern_id"] == "ignore_previous"
    assert len(body["pii_findings"]) == 1
    # match_analysis coerces back into the full model.
    assert body["match_analysis"]["experience_tier"] == "Senior"
    assert body["match_analysis"]["completeness"]["score"] == 90


def test_get_scan_original_text_is_safe_copy_not_raw(client_with_db_and_auth, db_session):
    """Phase 3 privacy invariant: raw original_text is never persisted, so the
    detail endpoint echoes the scrubbed safe copy into original_text. The two
    fields must be identical — there is no separate raw original on the server."""
    from conftest import TEST_USER_ID

    scan = _make_full_persisted_scan(db_session, TEST_USER_ID)

    body = client_with_db_and_auth.get(f"/scans/{scan.id}").json()
    assert body["original_text"] == body["safe_copy_text"]
    assert body["safe_copy_text"] == scan.safe_copy_text


def test_get_scan_other_users_scan_returns_404(client_with_db_and_auth, db_session):
    """Cross-tenant: a known scan_id owned by a DIFFERENT user returns 404,
    never 200 — no leak that the scan exists or what it contains."""
    from conftest import OTHER_USER_ID

    scan = _make_full_persisted_scan(db_session, OTHER_USER_ID)

    r = client_with_db_and_auth.get(f"/scans/{scan.id}")
    assert r.status_code == 404


def test_get_scan_org_colleague_returns_200(client_with_db_auth_and_org, db_session):
    """Org sharing: a scan created by a colleague but tagged with the caller's
    org is visible in the detail view, mirroring the list scope."""
    from conftest import OTHER_USER_ID, TEST_ORG_ID

    scan = _make_full_persisted_scan(db_session, OTHER_USER_ID, TEST_ORG_ID)

    r = client_with_db_auth_and_org.get(f"/scans/{scan.id}")
    assert r.status_code == 200
    assert r.json()["scan_id"] == str(scan.id)


def test_get_scan_other_org_returns_404(client_with_db_auth_and_org, db_session):
    """A scan in a DIFFERENT org returns 404 even to an authed caller in an org."""
    from conftest import OTHER_ORG_ID, OTHER_USER_ID

    scan = _make_full_persisted_scan(db_session, OTHER_USER_ID, OTHER_ORG_ID)

    r = client_with_db_auth_and_org.get(f"/scans/{scan.id}")
    assert r.status_code == 404


# ── Phase 7.2: free-tier quota gate on /scan-cv + /trust-report ──────────────

def _seed_persisted_scans(db_session, *, user_id, count):
    """Stuff `count` Scan rows for `user_id` into the current UTC month AND
    bump the Phase-8.1 MonthlyUsage counter so the atomic gate sees the same
    picture. Tests that previously relied on `COUNT(*) FROM scans` for the
    gate still work because both numbers move together."""
    from datetime import datetime, timezone
    from db_models import MonthlyUsage, Scan

    for i in range(count):
        db_session.add(
            Scan(
                user_id=user_id,
                filename=f"cv_{i}.pdf",
                risk_level="GREEN",
                risk_score=10,
                prompt_injection_findings=[],
                pii_findings=[],
                ai_text_likelihood="UNLIKELY",
                ai_text_score=0.1,
                safe_copy_text="x",
                summary="ok",
                match_analysis={"summary": "ok"},
            )
        )
    if count > 0:
        period = datetime.now(timezone.utc).strftime("%Y-%m")
        existing = (
            db_session.query(MonthlyUsage)
            .filter_by(user_id=user_id, period=period)
            .first()
        )
        if existing is None:
            db_session.add(
                MonthlyUsage(user_id=user_id, period=period, count=count)
            )
        else:
            existing.count = max(existing.count, count)
    db_session.commit()


def _make_user_pro(db_session, user_id):
    from datetime import datetime, timedelta, timezone

    from db_models import Subscription

    db_session.add(
        Subscription(
            user_id=user_id,
            stripe_customer_id=f"cus_{user_id}",
            stripe_subscription_id=f"sub_{user_id}",
            plan="pro",
            status="active",
            current_period_end=datetime.now(timezone.utc) + timedelta(days=30),
        )
    )
    db_session.commit()


def test_scan_cv_free_user_under_quota_succeeds(client_with_db_and_auth, db_session):
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT - 1)

    r = client_with_db_and_auth.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200


def test_scan_cv_free_user_at_quota_returns_402(client_with_db_and_auth, db_session):
    """Exactly at the cap: the next /scan-cv must be 402, NOT 200."""
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT)

    r = client_with_db_and_auth.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 402
    detail = r.json()["detail"]
    assert "Free plan limit reached" in detail
    assert "Upgrade to Pro" in detail
    assert str(FREE_SCAN_LIMIT) in detail


def test_scan_cv_free_user_over_quota_still_returns_402(client_with_db_and_auth, db_session):
    """Twelve scans already — quota gate stays on."""
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT + 2)

    r = client_with_db_and_auth.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 402


def test_scan_cv_pro_user_bypasses_quota(client_with_db_and_auth, db_session):
    """Pro user with 30 scans this month still scans. Subscription row flips
    the gate off regardless of count."""
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT + 20)
    _make_user_pro(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200


def test_scan_cv_anonymous_is_unmetered(client_with_db, db_session):
    """Anonymous demo path: no quota gate even when SOME user is at the cap.
    Anon callers have no user_id to count against, so the gate cannot apply."""
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT + 5)

    r = client_with_db.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200


def test_scan_cv_db_unconfigured_degrades_open(client_with_auth_only):
    """Auth configured but no DB → no way to count quota → must NOT 402.
    This preserves the Phase 4/5 backward-compat invariant for deployments
    that haven't enabled persistence yet."""
    r = client_with_auth_only.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200


def test_scan_cv_quota_counts_only_caller_not_org_colleague(
    client_with_db_auth_and_org, db_session
):
    """Phase 5 org sharing made colleagues' scans visible, but they must NOT
    count against the caller's free quota — the cap tracks who triggered the
    work."""
    from conftest import TEST_USER_ID, OTHER_USER_ID, TEST_ORG_ID
    from billing import FREE_SCAN_LIMIT

    # Colleague racked up 50 scans in the shared org; caller themselves has 0.
    from db_models import Scan
    for i in range(50):
        db_session.add(
            Scan(
                user_id=OTHER_USER_ID,
                org_id=TEST_ORG_ID,
                filename=f"col_{i}.pdf",
                risk_level="GREEN",
                risk_score=10,
                prompt_injection_findings=[],
                pii_findings=[],
                ai_text_likelihood="UNLIKELY",
                ai_text_score=0.1,
                safe_copy_text="x",
                summary="ok",
                match_analysis={"summary": "ok"},
            )
        )
    db_session.commit()

    r = client_with_db_auth_and_org.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200


def test_trust_report_free_user_at_quota_returns_402(client_with_db_and_auth, db_session):
    """The internal scan_cv call from /trust-report runs the quota gate too,
    so the PDF endpoint is not a quota bypass."""
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT)

    r = client_with_db_and_auth.post(
        "/trust-report",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 402


def test_trust_report_pro_user_bypasses_quota(client_with_db_and_auth, db_session):
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT + 1)
    _make_user_pro(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.post(
        "/trust-report",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"


# ── Phase 9 demo-access policy on /assessment ────────────────────────────────
# Supersedes the Phase 7.3 / 7.7 Pro gate. /assessment is now open to any
# signed-in caller (Free or Pro). The Pro differentiator moves to the
# follow-up endpoint (POST /assessment/followup — see Phase 9.2 tests).

def test_assessment_free_signed_in_cv_text_path_open(client_with_db_and_auth, db_session, monkeypatch):
    """Phase 9 — Free signed-in users can now generate one report (no 402).
    The 503 from no-API-key envs is the only barrier; with a mocked report
    function they get 200."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    import main as main_module

    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="ok",
        dimensions=[AssessmentDimension(name="X", text="Y")],
        overall_recommendation="Worth interviewing",
        overall_score=70,
        next_steps=["a", "b", "c"],
        provider_used="anthropic",
    )
    monkeypatch.setattr(main_module, "generate_assessment_report", lambda **kw: canned)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={
            "cv_text": "Sarah Chen, Senior Engineer. Python, AWS.",
            "role_context": "Senior backend.",
        },
    )
    assert r.status_code == 200


def test_assessment_free_signed_in_scan_id_path_open(client_with_db_and_auth, db_session, monkeypatch):
    """Phase 9 — Free signed-in users with their own scan can also run
    /assessment via scan_id."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    from conftest import TEST_USER_ID
    import main as main_module

    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)
    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="ok",
        dimensions=[AssessmentDimension(name="X", text="Y")],
        overall_recommendation="Worth interviewing",
        overall_score=70,
        next_steps=["a", "b", "c"],
        provider_used="anthropic",
    )
    monkeypatch.setattr(main_module, "generate_assessment_report", lambda **kw: canned)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={"scan_id": str(scan.id)},
    )
    assert r.status_code == 200


def test_assessment_pro_user_cv_text_path_works(client_with_db_and_auth, db_session, monkeypatch):
    """Pro signed-in user goes through. cv_text path does not persist
    (pre-Phase-7 invariant retained)."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    from conftest import TEST_USER_ID
    from db_models import Assessment
    import main as main_module

    _make_user_pro(db_session, TEST_USER_ID)

    canned = AssessmentReport(
        framework=FRAMEWORK_NAME,
        headline="x",
        dimensions=[AssessmentDimension(name="X", text="Y")],
        overall_recommendation="ok",
        overall_score=70,
        next_steps=["a", "b", "c"],
        provider_used="anthropic",
    )
    monkeypatch.setattr(main_module, "generate_assessment_report", lambda **kw: canned)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={"cv_text": "Sarah Chen, Senior Engineer. Python, AWS."},
    )
    assert r.status_code == 200
    # cv_text path stays ephemeral — no DB row written.
    assert db_session.query(Assessment).count() == 0


# Phase 7.7 — the old "anonymous happy path unchanged" assertion was removed.
# Codex P7 HIGH #3 showed that allowing anonymous /assessment let a denied Free
# user retry without the Authorization header to dodge the paywall, so /assessment
# now requires auth for every input mode. The replacement assertion lives in
# test_assessment_anonymous_returns_401_or_503 above.


# ── Phase 7.4: billing endpoints (/billing/status, /checkout-session, /portal) ─

def _must_not_call_stripe(**kwargs):
    raise AssertionError("Stripe layer must not be reached on this path")


def test_billing_status_free_user(client_with_db_and_auth, db_session):
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    _seed_persisted_scans(db_session, user_id=TEST_USER_ID, count=3)
    r = client_with_db_and_auth.get("/billing/status")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "free"
    assert body["is_pro"] is False
    assert body["scans_used"] == 3
    assert body["scan_limit"] == FREE_SCAN_LIMIT
    assert body["current_period_end"] is None
    assert body["status"] is None


def test_billing_status_pro_user(client_with_db_and_auth, db_session):
    from conftest import TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    r = client_with_db_and_auth.get("/billing/status")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert body["is_pro"] is True
    assert body["status"] == "active"
    assert body["current_period_end"] is not None


def test_billing_status_503_without_db(client_with_auth_only):
    r = client_with_auth_only.get("/billing/status")
    assert r.status_code == 503


def test_checkout_session_returns_url(client_with_db_and_auth, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "is_billing_configured", lambda: True)
    monkeypatch.setattr(
        main_module, "create_checkout_session",
        lambda **kw: "https://checkout.stripe.test/sess_123",
    )
    r = client_with_db_and_auth.post("/billing/checkout-session")
    assert r.status_code == 200
    assert r.json()["url"] == "https://checkout.stripe.test/sess_123"


def test_checkout_session_passes_user_and_existing_customer(
    client_with_db_and_auth, db_session, monkeypatch
):
    """The verified user_id (never client input) plus any known customer id are
    forwarded to the Stripe layer, so a re-subscribe reuses the same customer."""
    from conftest import TEST_USER_ID
    from db_models import Subscription
    import main as main_module

    # A lapsed (canceled) sub: not Pro, but we already hold their customer id.
    db_session.add(
        Subscription(
            user_id=TEST_USER_ID,
            stripe_customer_id="cus_known",
            stripe_subscription_id="sub_old",
            plan="pro",
            status="canceled",
            current_period_end=None,
        )
    )
    db_session.commit()

    captured = {}

    def fake_checkout(**kw):
        captured.update(kw)
        return "https://checkout.stripe.test/sess_123"

    monkeypatch.setattr(main_module, "is_billing_configured", lambda: True)
    monkeypatch.setattr(main_module, "create_checkout_session", fake_checkout)
    r = client_with_db_and_auth.post("/billing/checkout-session")
    assert r.status_code == 200
    assert captured["user_id"] == TEST_USER_ID
    assert captured["customer_id"] == "cus_known"


def test_checkout_session_409_when_already_pro(
    client_with_db_and_auth, db_session, monkeypatch
):
    from conftest import TEST_USER_ID
    import main as main_module

    _make_user_pro(db_session, TEST_USER_ID)
    monkeypatch.setattr(main_module, "is_billing_configured", lambda: True)
    monkeypatch.setattr(main_module, "create_checkout_session", _must_not_call_stripe)
    r = client_with_db_and_auth.post("/billing/checkout-session")
    assert r.status_code == 409


def test_checkout_session_503_when_billing_unconfigured(
    client_with_db_and_auth, monkeypatch
):
    import main as main_module

    monkeypatch.setattr(main_module, "is_billing_configured", lambda: False)
    monkeypatch.setattr(main_module, "create_checkout_session", _must_not_call_stripe)
    r = client_with_db_and_auth.post("/billing/checkout-session")
    assert r.status_code == 503


def test_checkout_session_503_without_db(client_with_auth_only):
    r = client_with_auth_only.post("/billing/checkout-session")
    assert r.status_code == 503


def test_checkout_session_maps_billing_error_to_503(
    client_with_db_and_auth, monkeypatch
):
    import main as main_module
    from stripe_billing import BillingError

    monkeypatch.setattr(main_module, "is_billing_configured", lambda: True)

    def boom(**kw):
        raise BillingError("Could not start checkout.")

    monkeypatch.setattr(main_module, "create_checkout_session", boom)
    r = client_with_db_and_auth.post("/billing/checkout-session")
    assert r.status_code == 503


def test_portal_returns_url(client_with_db_and_auth, db_session, monkeypatch):
    from conftest import TEST_USER_ID
    from db_models import Subscription
    import main as main_module

    db_session.add(
        Subscription(
            user_id=TEST_USER_ID,
            stripe_customer_id="cus_known",
            stripe_subscription_id="sub_1",
            plan="pro",
            status="active",
            current_period_end=None,
        )
    )
    db_session.commit()

    captured = {}

    def fake_portal(**kw):
        captured.update(kw)
        return "https://portal.stripe.test/p_1"

    monkeypatch.setattr(main_module, "is_billing_configured", lambda: True)
    monkeypatch.setattr(main_module, "create_portal_session", fake_portal)
    r = client_with_db_and_auth.post("/billing/portal")
    assert r.status_code == 200
    assert r.json()["url"] == "https://portal.stripe.test/p_1"
    assert captured["customer_id"] == "cus_known"


def test_portal_404_when_no_customer(client_with_db_and_auth, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "is_billing_configured", lambda: True)
    monkeypatch.setattr(main_module, "create_portal_session", _must_not_call_stripe)
    r = client_with_db_and_auth.post("/billing/portal")
    assert r.status_code == 404


def test_portal_503_when_billing_unconfigured(client_with_db_and_auth, monkeypatch):
    import main as main_module

    monkeypatch.setattr(main_module, "is_billing_configured", lambda: False)
    monkeypatch.setattr(main_module, "create_portal_session", _must_not_call_stripe)
    r = client_with_db_and_auth.post("/billing/portal")
    assert r.status_code == 503


def test_portal_503_without_db(client_with_auth_only):
    r = client_with_auth_only.post("/billing/portal")
    assert r.status_code == 503



# ── Phase 7.5: billing webhook (/billing/webhook) ────────────────────────────

def _post_webhook(client, event, *, monkeypatch, sig="t=1,v1=sig"):
    """POST a Stripe event through /billing/webhook with verify_and_parse_event
    stubbed to return `event`, so the test exercises dispatch + idempotency
    rather than the SDK signature math (that is unit-tested in test_billing.py)."""
    import main as main_module

    monkeypatch.setattr(
        main_module, "verify_and_parse_event", lambda payload, sig_header: event
    )
    return client.post(
        "/billing/webhook",
        content=b'{"stub": true}',
        headers={"stripe-signature": sig},
    )


def _sub_event(event_id, event_type, *, user_id, customer, sub_id, status, days):
    from datetime import datetime, timedelta, timezone

    period = int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": {
                "id": sub_id,
                "customer": customer,
                "status": status,
                "current_period_end": period,
                "metadata": {"user_id": user_id},
            }
        },
    }


def test_webhook_503_without_db(client_with_auth_only):
    # No DB -> 503 before any signature work happens.
    r = client_with_auth_only.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "x"}
    )
    assert r.status_code == 503


def test_webhook_400_on_bad_signature(client_with_db, monkeypatch):
    import main as main_module
    from stripe_billing import WebhookError

    def bad(payload, sig_header):
        raise WebhookError("Invalid webhook signature.")

    monkeypatch.setattr(main_module, "verify_and_parse_event", bad)
    r = client_with_db.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "bad"}
    )
    assert r.status_code == 400


def test_webhook_503_when_secret_unconfigured(client_with_db, monkeypatch):
    import main as main_module
    from stripe_billing import BillingError

    def unconfigured(payload, sig_header):
        raise BillingError("Billing webhook is not configured.")

    monkeypatch.setattr(main_module, "verify_and_parse_event", unconfigured)
    r = client_with_db.post(
        "/billing/webhook", content=b"{}", headers={"stripe-signature": "x"}
    )
    assert r.status_code == 503


def test_webhook_requires_no_auth(client_with_db, db_session, monkeypatch):
    # client_with_db has NO auth override; a valid event still processes (200).
    event = _sub_event(
        "evt_noauth", "customer.subscription.updated",
        user_id="user_webhook", customer="cus_1", sub_id="sub_1",
        status="active", days=30,
    )
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    assert r.json()["received"] is True


def test_webhook_subscription_created_makes_user_pro(client_with_db, db_session, monkeypatch):
    from billing import is_pro
    from db_models import Subscription

    event = _sub_event(
        "evt_active", "customer.subscription.created",
        user_id="user_pro", customer="cus_42", sub_id="sub_42",
        status="active", days=30,
    )
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    db_session.expire_all()
    sub = db_session.query(Subscription).filter_by(user_id="user_pro").first()
    assert sub is not None
    assert sub.status == "active"
    assert sub.stripe_customer_id == "cus_42"
    assert sub.stripe_subscription_id == "sub_42"
    assert is_pro("user_pro", db_session) is True


def test_webhook_subscription_deleted_cancels(client_with_db, db_session, monkeypatch):
    from billing import is_pro
    from db_models import Subscription

    _make_user_pro(db_session, "user_cancel")
    db_session.commit()
    assert is_pro("user_cancel", db_session) is True

    event = _sub_event(
        "evt_del", "customer.subscription.deleted",
        user_id="user_cancel", customer="cus_user_cancel", sub_id="sub_user_cancel",
        status="canceled", days=-1,
    )
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    db_session.expire_all()
    sub = db_session.query(Subscription).filter_by(user_id="user_cancel").first()
    assert sub.status == "canceled"
    assert is_pro("user_cancel", db_session) is False


def test_webhook_idempotent_duplicate_event_id(client_with_db, db_session, monkeypatch):
    from db_models import Subscription

    first = _sub_event(
        "evt_dup", "customer.subscription.updated",
        user_id="user_dup", customer="cus_d", sub_id="sub_d",
        status="active", days=30,
    )
    r1 = _post_webhook(client_with_db, first, monkeypatch=monkeypatch)
    assert r1.status_code == 200
    assert r1.json().get("duplicate") is None

    # Same event id, payload that WOULD cancel if reprocessed.
    second = _sub_event(
        "evt_dup", "customer.subscription.deleted",
        user_id="user_dup", customer="cus_d", sub_id="sub_d",
        status="canceled", days=30,
    )
    r2 = _post_webhook(client_with_db, second, monkeypatch=monkeypatch)
    assert r2.status_code == 200
    assert r2.json().get("duplicate") is True

    db_session.expire_all()
    sub = db_session.query(Subscription).filter_by(user_id="user_dup").first()
    assert sub.status == "active"  # duplicate skipped, not re-applied


def test_webhook_maps_by_customer_id_when_metadata_missing(
    client_with_db, db_session, monkeypatch
):
    from db_models import Subscription

    db_session.add(
        Subscription(
            user_id="user_fallback",
            stripe_customer_id="cus_fb",
            stripe_subscription_id="sub_fb",
            plan="pro",
            status="incomplete",
            current_period_end=None,
        )
    )
    db_session.commit()

    event = _sub_event(
        "evt_fb", "customer.subscription.updated",
        user_id="user_fallback", customer="cus_fb", sub_id="sub_fb",
        status="active", days=30,
    )
    # Strip the metadata so resolution must fall back to the customer id.
    event["data"]["object"]["metadata"] = {}
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    db_session.expire_all()
    sub = db_session.query(Subscription).filter_by(user_id="user_fallback").first()
    assert sub.status == "active"


def test_webhook_checkout_completed_captures_customer(
    client_with_db, db_session, monkeypatch
):
    from db_models import Subscription

    event = {
        "id": "evt_co",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "client_reference_id": "user_co",
                "customer": "cus_co",
                "subscription": "sub_co",
            }
        },
    }
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    sub = db_session.query(Subscription).filter_by(user_id="user_co").first()
    assert sub is not None
    assert sub.stripe_customer_id == "cus_co"
    assert sub.stripe_subscription_id == "sub_co"
    assert sub.status == "incomplete"  # not Pro until the subscription event


def test_webhook_unhandled_event_acknowledged_and_recorded(
    client_with_db, db_session, monkeypatch
):
    from db_models import WebhookEvent

    event = {"id": "evt_ping", "type": "ping", "data": {"object": {}}}
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    assert (
        db_session.query(WebhookEvent).filter_by(event_id="evt_ping").first()
        is not None
    )


def test_webhook_malformed_event_rejected(client_with_db, monkeypatch):
    event = {"data": {"object": {}}}  # no id / type
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 400


# ── Phase 7.7 hardening — proofs that the Codex P7 fixes work ─────────────────

def test_scan_cv_persist_query_param_is_ignored(client_with_db_and_auth, db_session):
    """Codex P7 HIGH #1: `?persist=false` used to suppress the Scan write so a
    Free user could scan forever without incrementing the quota. After 7.7
    the param doesn't exist on the public signature — the value is rejected
    by FastAPI's strict body extras or just ignored, and the row is always
    written for an authed caller."""
    from conftest import TEST_USER_ID
    from db_models import Scan

    r = client_with_db_and_auth.post(
        "/scan-cv?persist=false",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    rows = db_session.query(Scan).filter(Scan.user_id == TEST_USER_ID).all()
    assert len(rows) == 1, "?persist=false must NOT suppress the Scan write"


def test_trust_report_persists_scan_for_authed_caller(client_with_db_and_auth, db_session):
    """Codex P7 HIGH #2: /trust-report used to call scan_cv with persist=False,
    so it gave free users unlimited PDF reports without moving the quota.
    After 7.7 it shares the persist-always path and writes a Scan row."""
    from conftest import TEST_USER_ID
    from db_models import Scan

    r = client_with_db_and_auth.post(
        "/trust-report",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    rows = db_session.query(Scan).filter(Scan.user_id == TEST_USER_ID).all()
    assert len(rows) == 1


def test_trust_report_counts_toward_free_quota(client_with_db_and_auth, db_session):
    """Cap exhausted via /trust-report alone — proves the back door is closed."""
    from conftest import TEST_USER_ID
    from billing import FREE_SCAN_LIMIT

    for _ in range(FREE_SCAN_LIMIT):
        r = client_with_db_and_auth.post(
            "/trust-report",
            files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
        )
        assert r.status_code == 200
    # 11th call → 402
    r11 = client_with_db_and_auth.post(
        "/trust-report",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r11.status_code == 402


def test_webhook_skips_older_subscription_event(client_with_db, db_session, monkeypatch):
    """Codex P7 MED #1: out-of-order delivery — a stale `updated` event arriving
    AFTER a `deleted` event must NOT resurrect Pro access."""
    from datetime import datetime, timedelta, timezone

    from billing import is_pro

    now = int(datetime.now(timezone.utc).timestamp())

    # 1. Apply 'deleted' at t=now (newer).
    delete_event = _sub_event(
        "evt_del_1", "customer.subscription.deleted",
        user_id="user_ooo", customer="cus_ooo", sub_id="sub_ooo",
        status="canceled", days=-1,
    )
    delete_event["created"] = now
    r1 = _post_webhook(client_with_db, delete_event, monkeypatch=monkeypatch)
    assert r1.status_code == 200
    assert is_pro("user_ooo", db_session) is False

    # 2. Now a STALE 'updated' at t=now-60 arrives (older than the delete).
    stale_update = _sub_event(
        "evt_upd_old", "customer.subscription.updated",
        user_id="user_ooo", customer="cus_ooo", sub_id="sub_ooo",
        status="active", days=30,
    )
    stale_update["created"] = now - 60
    r2 = _post_webhook(client_with_db, stale_update, monkeypatch=monkeypatch)
    assert r2.status_code == 200  # Stripe gets 2xx so it stops retrying
    db_session.expire_all()
    assert is_pro("user_ooo", db_session) is False, (
        "stale 'updated' must NOT resurrect Pro access after 'deleted'"
    )


def test_webhook_refuses_customer_id_collision(client_with_db, db_session, monkeypatch):
    """Codex P7 MED #2: a signed event whose metadata.user_id is A but whose
    `customer` already belongs to a DIFFERENT user must be refused, not used
    to overwrite A's stripe_customer_id with B's."""
    from datetime import datetime, timezone

    from db_models import Subscription

    # User B owns cus_BBB. User A owns cus_AAA.
    db_session.add(
        Subscription(
            user_id="user_B", stripe_customer_id="cus_BBB",
            plan="pro", status="active",
        )
    )
    db_session.add(
        Subscription(
            user_id="user_A", stripe_customer_id="cus_AAA",
            plan="pro", status="active",
        )
    )
    db_session.commit()

    # Crafted event: metadata says user_A but customer is cus_BBB.
    event = _sub_event(
        "evt_collide", "customer.subscription.updated",
        user_id="user_A", customer="cus_BBB", sub_id="sub_evil",
        status="active", days=30,
    )
    event["created"] = int(datetime.now(timezone.utc).timestamp())

    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    # 2xx so Stripe stops retrying, but A's customer must NOT have flipped.
    assert r.status_code == 200
    db_session.expire_all()
    a = db_session.query(Subscription).filter_by(user_id="user_A").first()
    assert a.stripe_customer_id == "cus_AAA", (
        "user_A's stripe_customer_id must not change to user_B's customer id"
    )


def test_webhook_rejects_oversized_body_with_413(client_with_db):
    """Codex P7 round-2 LOW #1: /billing/webhook has its own 256 KB cap
    (Stripe events are kilobytes). Larger Content-Length → 413 before HMAC."""
    huge = b"x" * (300 * 1024)
    r = client_with_db.post(
        "/billing/webhook",
        content=huge,
        headers={"stripe-signature": "x", "content-length": str(len(huge))},
    )
    assert r.status_code == 413


def test_webhook_duplicate_event_race_returns_2xx(client_with_db, db_session, monkeypatch):
    """Codex P7 LOW #1: simulate the race where the pre-check passes for two
    concurrent deliveries of the same event_id. Achieved by inserting a
    WebhookEvent row that bypasses the pre-check, then sending the same
    event_id — the commit must catch IntegrityError and return duplicate 2xx,
    not 503."""
    from db_models import WebhookEvent

    event = _sub_event(
        "evt_dup_race", "customer.subscription.updated",
        user_id="user_race", customer="cus_race", sub_id="sub_race",
        status="active", days=30,
    )

    import main as main_module
    real_query = main_module.WebhookEvent

    # Patch the pre-check query so it returns None even though the row exists.
    # Easier: insert WebhookEvent AFTER the handler's pre-check but before its
    # commit. We simulate via monkeypatch: make the duplicate-check query
    # return None on first call, then insert a row, so the handler's add()
    # will collide on commit.
    inserted = {"done": False}

    real_first = main_module.Session.query

    # Simpler approach: insert the row mid-flight via verify_and_parse_event.
    def parse_and_insert(payload, sig_header):
        # Slip the duplicate row in here, so the handler's pre-check (which
        # runs AFTER us) actually sees the existing row and returns 2xx via
        # the "already exists" branch. That hits the same code path.
        if not inserted["done"]:
            db_session.add(WebhookEvent(event_id="evt_dup_race", event_type="x"))
            db_session.commit()
            inserted["done"] = True
        return event

    monkeypatch.setattr(main_module, "verify_and_parse_event", parse_and_insert)

    r = client_with_db.post(
        "/billing/webhook",
        content=b'{"stub": true}',
        headers={"stripe-signature": "x"},
    )
    assert r.status_code == 200
    assert r.json().get("duplicate") is True


# ── Phase 8.4 — org-admin Checkout + Portal ──────────────────────────────────

def _stub_stripe_for_billing(monkeypatch, *, url="https://checkout.test/x"):
    """Stub the Stripe layer so /billing endpoints return without hitting the
    network. Returns the captured kwargs dict so callers can assert metadata."""
    import main as main_module
    import stripe_billing

    monkeypatch.setattr(stripe_billing, "is_billing_configured", lambda: True)
    monkeypatch.setattr(main_module, "is_billing_configured", lambda: True)
    captured = {}

    def fake_checkout(**kwargs):
        captured.update(kwargs)
        return url

    monkeypatch.setattr(main_module, "create_checkout_session", fake_checkout)
    monkeypatch.setattr(main_module, "create_portal_session", lambda **kw: url)
    return captured


def test_billing_checkout_org_scope_admin_succeeds(
    client_with_db_auth_org_admin, monkeypatch
):
    """Admin in an active org can start an org-scope Checkout, metadata routed."""
    from conftest import TEST_USER_ID, TEST_ORG_ID

    captured = _stub_stripe_for_billing(monkeypatch)

    r = client_with_db_auth_org_admin.post("/billing/checkout-session?scope=org")
    assert r.status_code == 200, r.text
    assert r.json()["url"].startswith("https://")
    assert captured["scope"] == "org"
    assert captured["org_id"] == TEST_ORG_ID
    # The admin's user_id is still recorded for audit (not the org's customer).
    assert captured["user_id"] == TEST_USER_ID


def test_billing_checkout_org_scope_viewer_403(
    client_with_db_auth_org_viewer, monkeypatch
):
    """Non-admin org member cannot start an org subscription."""
    _stub_stripe_for_billing(monkeypatch)
    r = client_with_db_auth_org_viewer.post("/billing/checkout-session?scope=org")
    assert r.status_code == 403
    assert "admin" in r.json()["detail"].lower()


def test_billing_checkout_org_scope_without_org_context_400(
    client_with_db_and_auth, monkeypatch
):
    """Caller not currently inside an org → 400 (not 403; we don't have a role
    to check)."""
    _stub_stripe_for_billing(monkeypatch)
    r = client_with_db_and_auth.post("/billing/checkout-session?scope=org")
    assert r.status_code == 400


def test_billing_checkout_org_already_pro_returns_409(
    client_with_db_auth_org_admin, db_session, monkeypatch
):
    """The org already has an active sub — refuse 409 so we never start a
    second subscription on the same org's customer."""
    from datetime import datetime, timedelta, timezone
    from conftest import TEST_ORG_ID
    from db_models import OrganizationSubscription

    _stub_stripe_for_billing(monkeypatch)
    db_session.add(
        OrganizationSubscription(
            org_id=TEST_ORG_ID,
            stripe_customer_id="cus_org_existing",
            stripe_subscription_id="sub_org_existing",
            plan="pro",
            status="active",
            current_period_end=datetime.now(timezone.utc) + timedelta(days=10),
        )
    )
    db_session.commit()

    r = client_with_db_auth_org_admin.post("/billing/checkout-session?scope=org")
    assert r.status_code == 409


def test_billing_checkout_org_reuses_existing_customer_id(
    client_with_db_auth_org_admin, db_session, monkeypatch
):
    """An OrganizationSubscription row already carries a customer id (e.g. from
    a prior incomplete checkout); reuse it rather than creating a duplicate."""
    from conftest import TEST_ORG_ID
    from db_models import OrganizationSubscription

    captured = _stub_stripe_for_billing(monkeypatch)
    db_session.add(
        OrganizationSubscription(
            org_id=TEST_ORG_ID,
            stripe_customer_id="cus_org_reuse_me",
            plan="pro",
            status="incomplete",
        )
    )
    db_session.commit()

    r = client_with_db_auth_org_admin.post("/billing/checkout-session?scope=org")
    assert r.status_code == 200
    assert captured["customer_id"] == "cus_org_reuse_me"


def test_billing_checkout_user_scope_unaffected(
    client_with_db_and_auth, monkeypatch
):
    """The default scope=user path still works for non-org callers."""
    captured = _stub_stripe_for_billing(monkeypatch)
    r = client_with_db_and_auth.post("/billing/checkout-session")
    assert r.status_code == 200
    assert captured["scope"] == "user"
    assert captured.get("org_id") is None


def test_billing_portal_org_admin_succeeds(
    client_with_db_auth_org_admin, db_session, monkeypatch
):
    from conftest import TEST_ORG_ID
    from db_models import OrganizationSubscription

    _stub_stripe_for_billing(monkeypatch, url="https://portal.test/o")
    db_session.add(
        OrganizationSubscription(
            org_id=TEST_ORG_ID,
            stripe_customer_id="cus_org_portal",
            plan="pro",
            status="active",
        )
    )
    db_session.commit()

    r = client_with_db_auth_org_admin.post("/billing/portal?scope=org")
    assert r.status_code == 200
    assert r.json()["url"] == "https://portal.test/o"


def test_billing_portal_org_viewer_403(
    client_with_db_auth_org_viewer, monkeypatch
):
    _stub_stripe_for_billing(monkeypatch)
    r = client_with_db_auth_org_viewer.post("/billing/portal?scope=org")
    assert r.status_code == 403


def test_billing_status_via_org_flag_true_when_org_pro_only(
    client_with_db_auth_and_org, db_session
):
    """Free user in a Pro org: status reports plan=pro, is_pro=true, via_org=true."""
    from datetime import datetime, timedelta, timezone
    from conftest import TEST_ORG_ID
    from db_models import OrganizationSubscription

    db_session.add(
        OrganizationSubscription(
            org_id=TEST_ORG_ID,
            stripe_customer_id="cus_org",
            plan="pro",
            status="active",
            current_period_end=datetime.now(timezone.utc) + timedelta(days=10),
        )
    )
    db_session.commit()

    r = client_with_db_auth_and_org.get("/billing/status")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert body["is_pro"] is True
    assert body["via_org"] is True


def test_billing_status_via_org_false_when_personal_pro(
    client_with_db_and_auth, db_session
):
    """Personal Pro takes precedence: via_org=false even if there's a Pro org."""
    from conftest import TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    r = client_with_db_and_auth.get("/billing/status")
    assert r.status_code == 200
    body = r.json()
    assert body["plan"] == "pro"
    assert body["is_pro"] is True
    assert body["via_org"] is False


def test_scan_cv_free_user_in_pro_org_bypasses_quota(
    client_with_db_auth_and_org, db_session
):
    """Phase 8.3 view-everything: free user inside a Pro org gets unlimited
    scans (gate sees is_pro_for=True via org)."""
    from datetime import datetime, timedelta, timezone
    from conftest import TEST_USER_ID, TEST_ORG_ID
    from billing import FREE_SCAN_LIMIT
    from db_models import OrganizationSubscription

    db_session.add(
        OrganizationSubscription(
            org_id=TEST_ORG_ID,
            stripe_customer_id="cus_org",
            plan="pro",
            status="active",
            current_period_end=datetime.now(timezone.utc) + timedelta(days=10),
        )
    )
    _seed_persisted_scans(
        db_session, user_id=TEST_USER_ID, count=FREE_SCAN_LIMIT
    )
    # Without org Pro this would be 402; with it the 11th still succeeds.
    r = client_with_db_auth_and_org.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200


# ── Phase 8.5 — webhook routes org-scope events to OrganizationSubscription ──

def _org_sub_event(event_id, event_type, *, org_id, user_id, customer, sub_id, status, days):
    """An event whose metadata.scope=='org' so the 8.5 router puts it in
    org_subscriptions instead of subscriptions."""
    from datetime import datetime, timedelta, timezone

    period = int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
    return {
        "id": event_id,
        "type": event_type,
        "data": {
            "object": {
                "id": sub_id,
                "customer": customer,
                "status": status,
                "current_period_end": period,
                "metadata": {
                    "user_id": user_id,
                    "org_id": org_id,
                    "scope": "org",
                },
            }
        },
    }


def test_webhook_routes_org_subscription_to_org_table(client_with_db, db_session, monkeypatch):
    """metadata.scope=='org' goes to org_subscriptions; the per-user
    subscriptions table stays untouched."""
    from billing import is_org_pro, is_pro
    from db_models import OrganizationSubscription, Subscription

    event = _org_sub_event(
        "evt_org_created",
        "customer.subscription.created",
        org_id="org_paying_via_webhook",
        user_id="user_admin",
        customer="cus_org_1",
        sub_id="sub_org_1",
        status="active",
        days=30,
    )
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200

    db_session.expire_all()
    org_sub = (
        db_session.query(OrganizationSubscription)
        .filter_by(org_id="org_paying_via_webhook")
        .first()
    )
    assert org_sub is not None
    assert org_sub.status == "active"
    assert org_sub.stripe_customer_id == "cus_org_1"
    assert is_org_pro("org_paying_via_webhook", db_session) is True
    # User-scope table must not have been written.
    assert (
        db_session.query(Subscription).filter_by(user_id="user_admin").first()
        is None
    )
    # The admin who ran Checkout is NOT per-user Pro just because they
    # triggered the purchase.
    assert is_pro("user_admin", db_session) is False


def test_webhook_org_scope_canceled_clears_pro(client_with_db, db_session, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from billing import is_org_pro
    from db_models import OrganizationSubscription

    db_session.add(
        OrganizationSubscription(
            org_id="org_paying",
            stripe_customer_id="cus_org",
            stripe_subscription_id="sub_org",
            plan="pro",
            status="active",
            current_period_end=datetime.now(timezone.utc) + timedelta(days=10),
        )
    )
    db_session.commit()
    assert is_org_pro("org_paying", db_session) is True

    event = _org_sub_event(
        "evt_org_del",
        "customer.subscription.deleted",
        org_id="org_paying",
        user_id="user_admin",
        customer="cus_org",
        sub_id="sub_org",
        status="canceled",
        days=-1,
    )
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    db_session.expire_all()
    assert is_org_pro("org_paying", db_session) is False


def test_webhook_org_checkout_completed_records_customer(client_with_db, db_session, monkeypatch):
    """A checkout.session.completed with scope=org parks an incomplete row in
    org_subscriptions with the customer id so the org Portal works before the
    first subscription event lands."""
    from db_models import OrganizationSubscription

    event = {
        "id": "evt_cko_org",
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_org_checkout",
                "subscription": "sub_org_checkout",
                "metadata": {
                    "user_id": "user_admin",
                    "org_id": "org_in_checkout",
                    "scope": "org",
                },
            }
        },
    }
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    db_session.expire_all()
    row = (
        db_session.query(OrganizationSubscription)
        .filter_by(org_id="org_in_checkout")
        .first()
    )
    assert row is not None
    assert row.stripe_customer_id == "cus_org_checkout"
    assert row.status == "incomplete"


def test_webhook_org_scope_missing_org_id_is_ignored(client_with_db, db_session, monkeypatch):
    """Malformed org event (scope=org but no org_id) is logged + 2xx, never crashes."""
    from db_models import OrganizationSubscription

    event = {
        "id": "evt_org_bad",
        "type": "customer.subscription.created",
        "data": {
            "object": {
                "id": "sub_x",
                "customer": "cus_x",
                "status": "active",
                "current_period_end": 9999999999,
                "metadata": {"user_id": "user_admin", "scope": "org"},  # no org_id
            }
        },
    }
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    assert db_session.query(OrganizationSubscription).count() == 0


def test_webhook_pre_8_4_user_event_without_scope_still_routes_to_subscriptions(
    client_with_db, db_session, monkeypatch
):
    """Backwards-compat: existing subs in production may have metadata without
    a `scope` field. Missing scope defaults to 'user' (NOT 'org')."""
    from billing import is_pro
    from db_models import OrganizationSubscription, Subscription

    event = _sub_event(  # no scope key in the helper's payload
        "evt_legacy",
        "customer.subscription.created",
        user_id="user_legacy",
        customer="cus_legacy",
        sub_id="sub_legacy",
        status="active",
        days=30,
    )
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    db_session.expire_all()
    assert (
        db_session.query(Subscription).filter_by(user_id="user_legacy").first()
        is not None
    )
    assert is_pro("user_legacy", db_session) is True
    assert db_session.query(OrganizationSubscription).count() == 0


def test_webhook_org_customer_collision_refused(client_with_db, db_session, monkeypatch):
    """MED-#2 carried over to the org table: a customer_id that already belongs
    to a DIFFERENT org cannot be linked to ours."""
    from db_models import OrganizationSubscription

    db_session.add(
        OrganizationSubscription(
            org_id="org_owner",
            stripe_customer_id="cus_shared",
            plan="pro",
            status="active",
        )
    )
    db_session.commit()

    event = _org_sub_event(
        "evt_collide",
        "customer.subscription.updated",
        org_id="org_intruder",
        user_id="user_admin",
        customer="cus_shared",
        sub_id="sub_x",
        status="active",
        days=30,
    )
    r = _post_webhook(client_with_db, event, monkeypatch=monkeypatch)
    assert r.status_code == 200
    db_session.expire_all()
    assert (
        db_session.query(OrganizationSubscription)
        .filter_by(org_id="org_intruder")
        .first()
        is None
    )
    owner = (
        db_session.query(OrganizationSubscription)
        .filter_by(org_id="org_owner")
        .first()
    )
    assert owner.stripe_customer_id == "cus_shared"


# ── Phase 9 — POST /assessment/followup ─────────────────────────────────────

def _followup_body(scan_id, question="How strong is the AWS experience?"):
    return {"scan_id": str(scan_id), "question": question}


def test_followup_anonymous_returns_401_or_503():
    """Auth required (the dep raises 401 with Clerk configured, 503 in test
    env where it isn't)."""
    r = client.post(
        "/assessment/followup",
        json=_followup_body("00000000-0000-0000-0000-000000000000"),
    )
    assert r.status_code in (401, 503)


def test_followup_free_signed_in_returns_402(client_with_db_and_auth, db_session):
    """Same Pro gate as /assessment — a signed-in non-Pro user gets 402."""
    from conftest import TEST_USER_ID

    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.post(
        "/assessment/followup", json=_followup_body(scan.id)
    )
    assert r.status_code == 402
    assert "Pro subscription" in r.json()["detail"]


def test_followup_unknown_scan_id_returns_404(client_with_db_and_auth, db_session):
    """Caller is Pro, but the scan id doesn't exist — 404 with no leak."""
    from conftest import TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    r = client_with_db_and_auth.post(
        "/assessment/followup",
        json=_followup_body("00000000-0000-0000-0000-000000000000"),
    )
    assert r.status_code == 404


def test_followup_other_users_scan_id_returns_404(
    client_with_db_and_auth, db_session
):
    """IDOR check: a known scan owned by a DIFFERENT user returns 404, not
    200 — never leak that the scan exists or what's in it."""
    from conftest import OTHER_USER_ID, TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    foreign = _make_persisted_scan_for_user(db_session, OTHER_USER_ID)

    r = client_with_db_and_auth.post(
        "/assessment/followup", json=_followup_body(foreign.id)
    )
    assert r.status_code == 404


def test_followup_other_org_scan_returns_404(client_with_db_auth_and_org, db_session):
    """Same IDOR check for the Phase 5 org scope: a scan in a DIFFERENT org
    returns 404 even for a Pro caller in an org."""
    from conftest import OTHER_ORG_ID, OTHER_USER_ID, TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    foreign = _make_persisted_scan_for_user_org(
        db_session, OTHER_USER_ID, OTHER_ORG_ID
    )

    r = client_with_db_auth_and_org.post(
        "/assessment/followup", json=_followup_body(foreign.id)
    )
    assert r.status_code == 404


def test_followup_org_colleague_scan_returns_200(
    client_with_db_auth_and_org, db_session, monkeypatch
):
    """Org sharing: a Pro caller can ask a follow-up about a colleague's
    scan tagged with the same org id."""
    from conftest import OTHER_USER_ID, TEST_ORG_ID, TEST_USER_ID
    import main as main_module

    _make_user_pro(db_session, TEST_USER_ID)
    colleague_scan = _make_persisted_scan_for_user_org(
        db_session, OTHER_USER_ID, TEST_ORG_ID
    )
    monkeypatch.setattr(
        main_module,
        "generate_followup_answer",
        lambda **kw: "Sarah's AWS work is concrete — verify with the project owner.",
    )

    r = client_with_db_auth_and_org.post(
        "/assessment/followup", json=_followup_body(colleague_scan.id)
    )
    assert r.status_code == 200
    assert "Sarah" in r.json()["answer"]


def test_followup_question_too_long_returns_422(client_with_db_and_auth, db_session):
    """A 501-char question is rejected by the body validator before the LLM
    is touched."""
    from conftest import TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.post(
        "/assessment/followup",
        json={"scan_id": str(scan.id), "question": "x" * 501},
    )
    assert r.status_code == 422


def test_followup_empty_question_returns_422(client_with_db_and_auth, db_session):
    """A 0-char question is rejected — min_length=1."""
    from conftest import TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.post(
        "/assessment/followup",
        json={"scan_id": str(scan.id), "question": ""},
    )
    assert r.status_code == 422


def test_followup_invalid_scan_id_returns_422(client_with_db_and_auth, db_session):
    """A malformed UUID is rejected before the handler runs."""
    from conftest import TEST_USER_ID

    _make_user_pro(db_session, TEST_USER_ID)
    r = client_with_db_and_auth.post(
        "/assessment/followup",
        json={"scan_id": "not-a-uuid", "question": "ok"},
    )
    assert r.status_code == 422


def test_followup_pro_happy_path_returns_answer(
    client_with_db_and_auth, db_session, monkeypatch
):
    """Pro caller + valid own scan + mocked LLM → 200 with a non-empty answer.
    Server-side signals are passed to the LLM helper; client-supplied signals
    (if any) are NEVER forwarded — the body schema has no field for them."""
    from conftest import TEST_USER_ID
    import main as main_module

    _make_user_pro(db_session, TEST_USER_ID)
    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)

    captured = {}

    def fake_followup(**kw):
        captured.update(kw)
        return "Sarah is strong on AWS but lacks Kubernetes evidence."

    monkeypatch.setattr(main_module, "generate_followup_answer", fake_followup)

    r = client_with_db_and_auth.post(
        "/assessment/followup",
        json={
            "scan_id": str(scan.id),
            "question": "How strong is the AWS experience?",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["answer"].startswith("Sarah is strong")

    # The LLM helper was called with the recruiter's question verbatim AND
    # with server-derived signals + safe_copy (not from the request body).
    assert captured["question"] == "How strong is the AWS experience?"
    assert "risk_level" in captured["signals"]
    assert captured["cv_safe_copy"]  # non-empty


def test_followup_rate_limit_fires_at_sixth_call(
    client_with_db_and_auth, db_session, monkeypatch
):
    """5/min per-user cap — sixth call within the burst returns 429."""
    from conftest import TEST_USER_ID
    import main as main_module
    from rate_limit import reset_for_tests

    _make_user_pro(db_session, TEST_USER_ID)
    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)
    monkeypatch.setattr(
        main_module,
        "generate_followup_answer",
        lambda **kw: "ok.",
    )
    # The autouse conftest fixture already clears buckets, but be explicit
    # so a future ordering change can't make this test flaky.
    reset_for_tests()

    statuses = []
    for _ in range(6):
        r = client_with_db_and_auth.post(
            "/assessment/followup", json=_followup_body(scan.id)
        )
        statuses.append(r.status_code)

    # First five succeed, sixth is 429.
    assert statuses == [200, 200, 200, 200, 200, 429], f"statuses={statuses}"


def test_followup_no_db_returns_503(client_with_auth_only):
    """Auth configured but no DB → 503 (we can't look up the scan)."""
    r = client_with_auth_only.post(
        "/assessment/followup",
        json={
            "scan_id": "00000000-0000-0000-0000-000000000000",
            "question": "ok",
        },
    )
    assert r.status_code == 503
