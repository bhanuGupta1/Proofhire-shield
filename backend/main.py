"""ProofHire Shield — FastAPI backend, Phase 1."""
from __future__ import annotations
import io
import logging
import os
import re
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from models import (
    CompletenessResultModel,
    JDMatchRequest,
    JDMatchResultModel,
    MatchAnalysisModel,
    ScanResponse,
    ScanResult,
)
from jd_match import match_cv_to_jd
from scanner import compute_risk, scan_text
from safe_copy import generate_safe_copy
from trust_report import build_trust_report
from text_extract import extract_text, _MAGIC
from match_analysis import analyze_match

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ProofHire Shield API starting")
    yield
    logger.info("ProofHire Shield API stopped")


app = FastAPI(title="ProofHire Shield API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    # Check Content-Length before the body is buffered into memory.
    # Streaming/chunked uploads without Content-Length still hit the per-read cap below.
    cl = request.headers.get("content-length")
    if cl:
        try:
            if int(cl) > _MAX_UPLOAD_BYTES + 2048:
                return JSONResponse(status_code=413, content={"detail": "File exceeds 10 MB limit."})
        except ValueError:
            pass
    return await call_next(request)


_cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
_CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scan-cv", response_model=ScanResponse)
async def scan_cv(file: UploadFile = File(...)) -> ScanResponse:
    # Content-type guard
    if file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Unsupported file type: {file.content_type}. Upload PDF, DOCX, or TXT.",
        )

    raw = await file.read(_MAX_UPLOAD_BYTES + 1)
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File exceeds 10 MB limit.")

    filename = file.filename or "unknown"
    # Sanitise filename — no path traversal
    safe_name = _sanitise_filename(filename)

    # Declared type (extension) must match the content's magic bytes in BOTH
    # directions. 400 = wrong file type uploaded; 422 = correct type but unparseable.
    # A PDF/DOCX mislabelled .txt would otherwise be decoded as raw text, leaving its
    # hidden/metadata layers unscanned.
    lower = safe_name.lower()
    declared = (
        ".pdf" if lower.endswith(".pdf")
        else ".docx" if lower.endswith(".docx")
        else ".txt"
    )
    detected = next((ext for ext, magic in _MAGIC.items() if raw.startswith(magic)), ".txt")
    if declared != detected:
        raise HTTPException(
            status_code=400,
            detail="File content does not match declared type.",
        )

    try:
        text = extract_text(raw, safe_name)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    if not text.strip():
        raise HTTPException(status_code=422, detail="Could not extract text from file.")

    injection, pii, ai_score = scan_text(text)
    risk_level, risk_score = compute_risk(injection, pii, ai_score)

    if ai_score >= 0.6:
        ai_label = "LIKELY"
    elif ai_score >= 0.3:
        ai_label = "POSSIBLE"
    else:
        ai_label = "UNLIKELY"

    safe_copy = generate_safe_copy(text, injection, pii)
    match = analyze_match(text)

    summary_parts = []
    if injection:
        summary_parts.append(
            f"{len(injection)} hidden instruction(s) found — do not paste this CV into an AI tool."
        )
    if pii:
        summary_parts.append(f"{len(pii)} personal data item(s) flagged.")
    if ai_label != "UNLIKELY":
        summary_parts.append(f"Text {ai_label.lower()} written by AI.")
    if not summary_parts:
        summary_parts.append("No issues detected. CV appears safe for AI workflow use.")

    result = ScanResult(
        filename=safe_name,
        risk_level=risk_level,
        risk_score=risk_score,
        prompt_injection_findings=injection,
        pii_findings=pii,
        ai_text_likelihood=ai_label,
        ai_text_score=round(ai_score, 3),
        original_text=text,
        safe_copy_text=safe_copy,
        summary=" ".join(summary_parts),
        match_analysis=MatchAnalysisModel(
            skills=match.skills,
            experience_tier=match.experience_tier,
            years_experience=match.years_experience,
            education_level=match.education_level,
            interview_probes=match.interview_probes,
            key_claims=match.key_claims,
            total_skills_found=match.total_skills_found,
            summary=match.summary,
            completeness=CompletenessResultModel(
                score=match.completeness.score,
                breakdown=match.completeness.breakdown,
            ),
        ),
    )
    return ScanResponse(ok=True, result=result)


@app.post("/trust-report")
async def trust_report(file: UploadFile = File(...)) -> Response:
    """Re-scan the CV and return a Trust Report PDF."""
    scan = await scan_cv(file)
    if not scan.result:
        raise HTTPException(status_code=500, detail="Scan failed.")
    pdf_bytes = build_trust_report(scan.result)
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="trust-report-{scan.result.filename}.pdf"'
        },
    )


@app.post("/match-jd", response_model=JDMatchResultModel)
def match_jd(req: JDMatchRequest) -> JDMatchResultModel:
    """Score a CV's skills against a pasted job description. Text-only, no upload."""
    result = match_cv_to_jd(req.cv_text, req.jd_text)
    return JDMatchResultModel(
        match_score=result.match_score,
        matched_skills=result.matched_skills,
        missing_skills=result.missing_skills,
        bonus_skills=result.bonus_skills,
    )


def _sanitise_filename(name: str) -> str:
    """Strip directory components and unsafe characters from a filename."""
    base = os.path.basename(name)
    safe = re.sub(r"[^\w.\-]", "_", base)
    return safe[:128] or "upload"
