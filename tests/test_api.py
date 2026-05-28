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


# ── Magic-bytes guard ─────────────────────────────────────────────────────────

def test_fake_pdf_content_type_returns_422():
    """Binary garbage claiming to be PDF → 422, not 500."""
    r = _post_file(content=b"This is not a PDF at all",
                   filename="evil.pdf", content_type="application/pdf")
    assert r.status_code == 422
    assert r.json()["detail"]  # error message present


def test_fake_docx_content_type_returns_422():
    r = _post_file(
        content=b"Not a DOCX either",
        filename="evil.docx",
        content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    assert r.status_code == 422


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


def test_trust_report_bad_file_returns_422():
    r = _post_file(content=b"garbage", filename="bad.pdf",
                   content_type="application/pdf", endpoint="/trust-report")
    assert r.status_code == 422
