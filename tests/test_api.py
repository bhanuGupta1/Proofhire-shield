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


def test_scan_cv_returns_scan_id_when_db_available(client_with_db):
    r = client_with_db.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    body = r.json()["result"]
    assert body["scan_id"] is not None
    # Must be a valid UUID string (no sequential integers).
    import uuid as _uuid

    parsed = _uuid.UUID(body["scan_id"])
    assert str(parsed) == body["scan_id"]


def test_scan_cv_persists_safe_copy_only_no_original(client_with_db, db_session):
    """Privacy invariant: the persisted row stores safe_copy_text but NEVER the
    raw original_text. We assert by inspecting the table directly."""
    from db_models import Scan

    r = client_with_db.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    assert r.status_code == 200
    rows = db_session.query(Scan).all()
    assert len(rows) == 1
    row = rows[0]
    assert row.filename == "01_clean.pdf"
    assert row.safe_copy_text  # non-empty
    # The Scan model has no original_text column at all; assert at the schema level.
    assert "original_text" not in {c.name for c in Scan.__table__.columns}


def test_scan_cv_response_scan_id_matches_db_row(client_with_db, db_session):
    from db_models import Scan

    r = client_with_db.post(
        "/scan-cv",
        files={"file": ("01_clean.pdf", (DEMO_DIR / "01_clean.pdf").read_bytes(), "application/pdf")},
    )
    body_scan_id = r.json()["result"]["scan_id"]
    rows = db_session.query(Scan).all()
    assert len(rows) == 1
    assert str(rows[0].id) == body_scan_id


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
