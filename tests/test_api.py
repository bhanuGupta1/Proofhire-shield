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
    r = client.post("/match-jd", json={"cv_text": "Python, AWS, Docker.", "jd_text": "Need Python."})
    assert r.status_code == 200
    body = r.json()
    assert body["match_score"] >= 70
    assert "Python" in body["matched_skills"]


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


def test_assessment_endpoint_503_without_api_key(monkeypatch):
    """503 detail must not disclose whether EITHER API key is configured."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    r = client.post("/assessment", json=_assessment_body())
    assert r.status_code == 503
    detail = r.json()["detail"]
    assert "ANTHROPIC_API_KEY" not in detail
    assert "GROQ_API_KEY" not in detail
    assert "temporarily unavailable" in detail.lower()


def test_assessment_endpoint_happy_path(monkeypatch):
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

    r = client.post("/assessment", json=_assessment_body())
    assert r.status_code == 200
    body = r.json()
    assert body["framework"] == FRAMEWORK_NAME
    assert body["overall_score"] == 78
    assert len(body["next_steps"]) == 3


def test_assessment_endpoint_validates_required_fields():
    # Missing cv_text -> 422.
    r = client.post("/assessment", json={"role_context": "x"})
    assert r.status_code == 422


def test_assessment_endpoint_oversized_cv_text_rejected():
    body = _assessment_body()
    body["cv_text"] = "x" * 20001
    r = client.post("/assessment", json=body)
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


def test_assessment_scan_id_without_auth_returns_401():
    """Phase 4: anonymous calls cannot use scan_id at all (auth checked first)."""
    r = client.post(
        "/assessment",
        json={"scan_id": "00000000-0000-0000-0000-000000000000"},
    )
    assert r.status_code == 401


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


def test_assessment_requires_exactly_one_of_cv_text_or_scan_id():
    # Neither → 422.
    r1 = client.post("/assessment", json={"role_context": "Backend engineer"})
    assert r1.status_code == 422
    # Both → 422 (we don't silently drop cv_text in favour of scan_id).
    r2 = client.post(
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


def test_assessment_with_cv_text_path_does_not_persist(client_with_db, db_session, monkeypatch):
    """cv_text-only assessments are intentionally NOT persisted in Phase 3 —
    Phase 4 (auth) will revisit per-recruiter history."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    from db_models import Assessment
    import main as main_module

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

    r = client_with_db.post(
        "/assessment",
        json={"cv_text": "Sarah Chen, Senior Engineer."},
    )
    assert r.status_code == 200
    rows = db_session.query(Assessment).all()
    assert len(rows) == 0  # explicitly NOT persisted


def test_assessment_endpoint_ignores_client_supplied_trust_claims(monkeypatch):
    """The endpoint must not honour client-supplied match_analysis / risk_signals.
    Pydantic ignores extra fields by default, so smuggling them is silently dropped."""
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
    r = client.post("/assessment", json=body)
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
    """Stuff `count` Scan rows for `user_id` into the current UTC month so the
    quota counter sees them. Minimal field set (the quota query only cares
    about user_id + created_at)."""
    from db_models import Scan

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


# ── Phase 7.3: Pro gate on /assessment ───────────────────────────────────────

def test_assessment_free_signed_in_user_returns_402(client_with_db_and_auth, db_session):
    """A signed-in caller without an active Pro subscription gets 402 on
    /assessment, regardless of cv_text vs scan_id input."""
    r = client_with_db_and_auth.post(
        "/assessment",
        json={
            "cv_text": "Sarah Chen, Senior Engineer. Python, AWS.",
            "role_context": "Senior backend.",
        },
    )
    assert r.status_code == 402
    assert "Pro subscription" in r.json()["detail"]


def test_assessment_free_signed_in_scan_id_path_also_blocked(client_with_db_and_auth, db_session):
    """scan_id input mode hits the Pro gate too — free user with a valid own
    scan still gets 402, not 200, not 404."""
    from conftest import TEST_USER_ID

    scan = _make_persisted_scan_for_user(db_session, TEST_USER_ID)

    r = client_with_db_and_auth.post(
        "/assessment",
        json={"scan_id": str(scan.id)},
    )
    assert r.status_code == 402


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


def test_assessment_anonymous_happy_path_unchanged(monkeypatch):
    """The public demo path must still return 200 for anonymous callers.
    Phase 7.3's gate is keyed on current_user; anon (no Clerk token) skips it."""
    from assessment import AssessmentDimension, AssessmentReport, FRAMEWORK_NAME
    import main as main_module

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

    r = client.post(
        "/assessment",
        json={"cv_text": "Sarah Chen, Senior Engineer."},
    )
    assert r.status_code == 200
