"""ProofHire Shield — FastAPI backend, Phase 1."""
from __future__ import annotations
import io
import logging
import os
import re
import sys
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models import (
    AssessmentDimensionModel,
    AssessmentReportModel,
    AssessmentRequest,
    CompletenessResultModel,
    JDMatchRequest,
    JDMatchResultModel,
    MatchAnalysisModel,
    ScanResponse,
    ScanResult,
)
from dataclasses import asdict
from jd_match import match_cv_to_jd
from assessment import AssessmentError, generate_assessment_report
from scanner import compute_risk, scan_text
from safe_copy import generate_safe_copy
from trust_report import build_trust_report
from text_extract import extract_text, _MAGIC
from match_analysis import analyze_match
from db import get_db
from db_models import Assessment, Scan
from auth import get_current_user_optional

logger = logging.getLogger(__name__)
logging.basicConfig(stream=sys.stdout, level=logging.INFO)

_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_PERSISTED_TEXT_CHARS = 64 * 1024  # 64 KB cap on text fields written to DB
_ALLOWED_CONTENT_TYPES = {
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "text/plain",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("ProofHire Shield API starting")
    # If a database is configured, bring its schema up to head before serving
    # traffic. Migration failure is fatal — better to fail loud than to serve
    # writes against a stale schema.
    if os.environ.get("DATABASE_URL"):
        try:
            from alembic.config import Config
            from alembic import command as alembic_command

            cfg = Config("alembic.ini")
            alembic_command.upgrade(cfg, "head")
            logger.info("Database migrations applied")
        except Exception:
            logger.exception("Database migrations failed")
            raise
    yield
    logger.info("ProofHire Shield API stopped")


app = FastAPI(title="ProofHire Shield API", version="0.1.0", lifespan=lifespan)


@app.middleware("http")
async def limit_body_size(request: Request, call_next):
    # POST endpoints require Content-Length so we can reject oversized bodies BEFORE
    # buffering them. Without this, a chunked request lacking CL slips straight past.
    if request.method == "POST":
        cl = request.headers.get("content-length")
        if cl is None:
            return JSONResponse(status_code=411, content={"detail": "Length Required."})
        try:
            if int(cl) > _MAX_UPLOAD_BYTES + 2048:
                return JSONResponse(status_code=413, content={"detail": "Request body exceeds limit."})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length."})
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
async def scan_cv(
    file: UploadFile = File(...),
    db: Session | None = Depends(get_db),
    persist: bool = True,
    current_user: str | None = Depends(get_current_user_optional),
) -> ScanResponse:
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
            red_flags=match.red_flags,
        ),
    )

    # Persistence is best-effort AND requires an authenticated caller (Phase 4).
    # Anonymous callers always get the in-memory result without a scan_id, so
    # nothing reaches the database without a known owner. Storage caps prevent
    # one authed user from rapidly filling the table by uploading near-cap text.
    if db is not None and persist and current_user is not None:
        try:
            row = Scan(
                user_id=current_user,
                filename=result.filename[:256],
                risk_level=result.risk_level,
                risk_score=result.risk_score,
                prompt_injection_findings=[f.model_dump() for f in result.prompt_injection_findings],
                pii_findings=[f.model_dump() for f in result.pii_findings],
                ai_text_likelihood=result.ai_text_likelihood,
                ai_text_score=result.ai_text_score,
                safe_copy_text=result.safe_copy_text[:_MAX_PERSISTED_TEXT_CHARS],
                summary=result.summary[:_MAX_PERSISTED_TEXT_CHARS],
                match_analysis=result.match_analysis.model_dump(),
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            result.scan_id = str(row.id)
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Failed to persist scan")

    return ScanResponse(ok=True, result=result)


@app.post("/trust-report")
async def trust_report(
    file: UploadFile = File(...),
    db: Session | None = Depends(get_db),
    current_user: str | None = Depends(get_current_user_optional),
) -> Response:
    """Re-scan the CV and return a Trust Report PDF."""
    # Pass db + current_user explicitly: when this endpoint calls scan_cv as a
    # regular Python function the FastAPI Depends machinery does not fire, so
    # the defaults would be the Depends marker rather than real values.
    # persist=False so PDF generation does not silently double-write a scan row
    # the caller neither requested nor receives a scan_id for.
    scan = await scan_cv(file, db=db, persist=False, current_user=current_user)
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


@app.post("/assessment", response_model=AssessmentReportModel)
def assessment_endpoint(
    req: AssessmentRequest,
    db: Session | None = Depends(get_db),
    current_user: str | None = Depends(get_current_user_optional),
) -> AssessmentReportModel:
    """Generate a structured ProofHire v1 candidate assessment.

    Two input modes:
    - `scan_id`: requires authentication. Loads the caller's own Scan row
      (filtered by user_id so a known UUID belonging to another user returns
      404, not 200), reuses its safe_copy_text + signals, persists the Assessment.
    - `cv_text`: anonymous-allowed. Re-runs Phase-1 in memory, generates,
      does NOT persist (per-user history requires authentication AND scan_id).
    Requires ANTHROPIC_API_KEY or GROQ_API_KEY on the server; returns 503 otherwise.
    """
    if req.scan_id:
        if current_user is None:
            raise HTTPException(
                status_code=401,
                detail="Authentication required to use scan_id.",
            )
        if db is None:
            raise HTTPException(
                status_code=503,
                detail="scan_id requires a configured database.",
            )
        # Scope by user_id so a known scan UUID belonging to a different user
        # returns 404 rather than 200.
        scan_row = (
            db.query(Scan)
            .filter_by(id=req.scan_id, user_id=current_user)
            .first()
        )
        if scan_row is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        cv_safe_copy = scan_row.safe_copy_text
        signals = {
            "risk_level": scan_row.risk_level,
            "risk_score": scan_row.risk_score,
            "injection_count": len(scan_row.prompt_injection_findings or []),
            "ai_text_likelihood": scan_row.ai_text_likelihood,
            "match": scan_row.match_analysis,
        }
        # End the read transaction before the slow LLM call so we don't pin a
        # pooled connection while waiting on Anthropic/Groq.
        db.commit()
    else:
        # cv_text path: re-derive everything server-side. Never trust client signals.
        injection, pii, ai_score = scan_text(req.cv_text)
        risk_level, risk_score = compute_risk(injection, pii, ai_score)
        match = analyze_match(req.cv_text)
        cv_safe_copy = generate_safe_copy(req.cv_text, injection, pii)
        if ai_score >= 0.6:
            ai_label = "LIKELY"
        elif ai_score >= 0.3:
            ai_label = "POSSIBLE"
        else:
            ai_label = "UNLIKELY"
        signals = {
            "risk_level": risk_level,
            "risk_score": risk_score,
            "injection_count": len(injection),
            "ai_text_likelihood": ai_label,
            "match": asdict(match),
        }

    try:
        report = generate_assessment_report(
            cv_safe_copy=cv_safe_copy,
            signals=signals,
            role_context=req.role_context,
        )
    except AssessmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    # Persist the Assessment only when it is anchored to a Scan in the DB AND
    # the caller is authenticated. cv_text-only / anonymous assessments stay
    # ephemeral. user_id is denormalised onto the row so per-user list queries
    # do not always need a join through scans.
    if req.scan_id and db is not None and current_user is not None:
        try:
            row = Assessment(
                scan_id=req.scan_id,
                user_id=current_user,
                framework=report.framework,
                headline=report.headline,
                dimensions=[asdict(d) for d in report.dimensions],
                overall_recommendation=report.overall_recommendation,
                overall_score=report.overall_score,
                next_steps=report.next_steps,
                provider_used=report.provider_used or "unknown",
            )
            db.add(row)
            db.commit()
        except SQLAlchemyError:
            db.rollback()
            logger.exception("Failed to persist assessment")

    return AssessmentReportModel(
        framework=report.framework,
        headline=report.headline,
        dimensions=[
            AssessmentDimensionModel(name=d.name, text=d.text, bullets=d.bullets)
            for d in report.dimensions
        ],
        overall_recommendation=report.overall_recommendation,
        overall_score=report.overall_score,
        next_steps=report.next_steps,
    )


def _sanitise_filename(name: str) -> str:
    """Strip directory components and unsafe characters from a filename."""
    base = os.path.basename(name)
    safe = re.sub(r"[^\w.\-]", "_", base)
    return safe[:128] or "upload"
