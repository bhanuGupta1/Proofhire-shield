"""ProofHire Shield — FastAPI backend, Phase 1."""
from __future__ import annotations
import io
import logging
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from models import (
    AssessmentDimensionModel,
    AssessmentReportModel,
    AssessmentRequest,
    BillingRedirectResponse,
    BillingStatusResponse,
    CompletenessResultModel,
    FollowupRequest,
    FollowupResponse,
    JDMatchRequest,
    JDMatchResultModel,
    MatchAnalysisModel,
    ScanListResponse,
    ScanResponse,
    ScanResult,
    ScanSummary,
)
from dataclasses import asdict
from jd_match import match_cv_to_jd
from assessment import (
    AssessmentError,
    generate_assessment_report,
    generate_followup_answer,
)
from scanner import compute_risk, scan_text
from safe_copy import generate_safe_copy
from trust_report import build_trust_report
from text_extract import extract_text, _MAGIC
from match_analysis import analyze_match
from db import get_db
from db_models import (
    Assessment,
    OrganizationSubscription,
    Scan,
    Subscription,
    WebhookEvent,
)
from auth import (
    get_current_org_optional,
    get_current_org_role_optional,
    get_current_user,
    get_current_user_optional,
)
from billing import (
    FREE_ASSESSMENT_LIMIT,
    FREE_SCAN_LIMIT,
    assessments_used_this_month,
    consume_assessment_or_refuse,
    consume_or_refuse,
    is_org_pro,
    is_pro,
    is_pro_for,
    quota_used_this_month,
)
from rate_limit import (
    ANON_PER_MIN,
    AUTH_FREE_PER_MIN,
    AUTH_PRO_PER_MIN,
    check_rate,
)
from stripe_billing import (
    BillingError,
    WebhookError,
    create_checkout_session,
    create_portal_session,
    is_billing_configured,
    verify_and_parse_event,
)
from routers import candidates as candidates_router
from routers import dashboard as dashboard_router
from routers import jobs as jobs_router
from routers import matching as matching_router
from routers import pipeline as pipeline_router
from routers import reports as reports_router

logger = logging.getLogger(__name__)


# Phase 8.6 — request-scoped logging context. A middleware sets a fresh
# request_id on every inbound request; routes may push user_id / org_id once
# the Clerk deps resolve. The filter below copies whatever is in the context
# onto each LogRecord, so every warning / exception line emitted under a
# request automatically carries its correlation id.
_request_ctx: ContextVar[dict[str, str]] = ContextVar("_request_ctx", default={})


def _push_request_context(**fields: str) -> None:
    """Add/update keys on the current request's logging context.

    Endpoints call this once the Clerk deps have resolved so subsequent
    `logger.warning(...)` lines under the same request carry user/org info."""
    ctx = dict(_request_ctx.get())
    for k, v in fields.items():
        if v:
            ctx[k] = v
    _request_ctx.set(ctx)


class _RequestContextFilter(logging.Filter):
    """Inject request_id / user_id / org_id onto every LogRecord."""

    def filter(self, record: logging.LogRecord) -> bool:  # noqa: A003 (logging API)
        ctx = _request_ctx.get()
        record.request_id = ctx.get("request_id", "-")
        record.user_id = ctx.get("user_id", "-")
        record.org_id = ctx.get("org_id", "-")
        return True


logging.basicConfig(
    stream=sys.stdout,
    level=logging.INFO,
    format=(
        "%(asctime)s %(levelname)s %(name)s "
        "rid=%(request_id)s user=%(user_id)s org=%(org_id)s | %(message)s"
    ),
)
# The filter has to live on a handler, not on a logger — a Logger.addFilter
# only fires for records emitted THROUGH that logger directly; records that
# propagate up from a child logger bypass it. Handler filters always run.
_REQUEST_CTX_FILTER = _RequestContextFilter()
for _h in logging.getLogger().handlers:
    _h.addFilter(_REQUEST_CTX_FILTER)

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


@app.middleware("http")
async def followup_preauth_rate_middleware(request: Request, call_next):
    """Phase 9.5 (Codex P9 round-2 LOW) — path-scoped IP rate limit on
    /assessment/followup that fires BEFORE body parsing AND dep resolution.

    The first P9 fix used a Depends() to rate-limit ahead of get_current_user,
    but Pydantic body validation (`req: FollowupRequest`) ran before deps, so
    a malformed-JSON flood returned 422 without ever touching the IP bucket.
    Middleware runs above both, so a 422 from a forged body still consumes a
    token and an anonymous flood is bounded.

    Keeps the existing in-handler per-user 5/min bucket (separate identity
    key `user:<sub>`, no cross-pollination with this anon `ip:<addr>` bucket).
    """
    if (
        request.method == "POST"
        and request.url.path == "/assessment/followup"
    ):
        identity = "ip:" + _client_ip(request)
        allowed, retry_after = check_rate(
            "/assessment/followup-preauth", identity, per_min=ANON_PER_MIN
        )
        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Too many requests. Please slow down."},
                headers={"Retry-After": str(int(retry_after) + 1)},
            )
    return await call_next(request)


@app.middleware("http")
async def request_id_middleware(request: Request, call_next):
    """Phase 8.6 — every request gets a fresh request_id (or honours an inbound
    X-Request-Id from the client / upstream proxy). The id flows into the
    logging context and is echoed back in the response header so log lines and
    the response can be correlated.

    Declared LAST so it's the OUTERMOST middleware (Starlette/FastAPI applies
    decorators bottom-up): it must set the context-var before limit_body_size
    can produce its 411/413 response, and it must inject the X-Request-Id
    header onto every response, including the 411/413 ones."""
    inbound = request.headers.get("x-request-id", "").strip()
    # Cap inbound to 64 chars so a hostile client can't blow up the log lines.
    rid = inbound[:64] if inbound else uuid.uuid4().hex
    _request_ctx.set({"request_id": rid})
    response = await call_next(request)
    response.headers["x-request-id"] = rid
    return response


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate-limit keying. Trusts the leftmost
    X-Forwarded-For on the HF Spaces + Cloudflare path (both layers attach
    the original IP); behind any other proxy this needs review.

    Returns a sentinel string when no IP is available rather than a real
    address; the value is only ever used as a bucket key, never to bind."""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate(
    route: str,
    request: Request,
    current_user: str | None = None,
    db: Session | None = None,
) -> None:
    """Phase 8.2 — token-bucket gate. 429 with Retry-After when exhausted.

    Identity: authed callers by Clerk user_id (server-verified claim), anon
    callers by client IP. Rate: anon < free < Pro. Pro recognition is
    best-effort — if `db` is None or the lookup fails we treat the caller
    as Free, which only narrows the bucket (never widens it).
    """
    if current_user is None:
        identity = "ip:" + _client_ip(request)
        per_min = ANON_PER_MIN
    else:
        identity = "user:" + current_user
        per_min = (
            AUTH_PRO_PER_MIN
            if db is not None and is_pro(current_user, db)
            else AUTH_FREE_PER_MIN
        )
    allowed, retry_after = check_rate(route, identity, per_min)
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many requests. Please try again shortly.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )


_cors_raw = os.environ.get("CORS_ORIGINS", "http://localhost:5173")
_CORS_ORIGINS = [o.strip() for o in _cors_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    # PATCH/DELETE added for the platform CRUD routers (candidates, jobs, …).
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

# Platform feature routers (candidates, jobs, …) — mounted alongside the core
# scan endpoints rather than appended to this file.
app.include_router(candidates_router.router)
app.include_router(jobs_router.router)
app.include_router(pipeline_router.router)
app.include_router(matching_router.router)
app.include_router(dashboard_router.router)
app.include_router(reports_router.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/scan-cv", response_model=ScanResponse)
async def scan_cv(
    request: Request,
    file: UploadFile = File(...),
    db: Session | None = Depends(get_db),
    current_user: str | None = Depends(get_current_user_optional),
    current_org: str | None = Depends(get_current_org_optional),
    match_engine: str = "llm",
) -> ScanResponse:
    # Phase 8.6 — push the resolved identity into the log context so every
    # log line under this request carries user/org alongside the request_id.
    _push_request_context(user_id=current_user or "", org_id=current_org or "")

    # Phase 8.2 — rate limit (anon=30/min, free=100/min, pro=300/min by identity)
    # fires before the quota gate, so an abusive caller never even consumes
    # their monthly bucket on rejected requests.
    _enforce_rate("/scan-cv", request, current_user, db)

    # Phase 7.2 + 8.1 + 8.3 — free-tier quota gate, atomic via consume_or_refuse.
    # Anonymous (no current_user) is unmetered so the demo path keeps working;
    # DB-unconfigured deployments degrade open (Phase 4/5 backward-compat
    # invariant). EFFECTIVE Pro (personal OR org-Pro for the active org)
    # bypasses unconditionally. Checked first so a free user at the cap never
    # pays the file-read cost. consume_or_refuse RESERVES the slot before the
    # scan runs — a failed scan still counts (conservative), which avoids a
    # refund race and matches "reservation, not optimistic".
    if (
        current_user is not None
        and db is not None
        and not is_pro_for(current_user, current_org, db)
    ):
        if not consume_or_refuse(current_user, db):
            raise HTTPException(
                status_code=402,
                detail=(
                    f"Free plan limit reached ({FREE_SCAN_LIMIT} scans this month). "
                    "Upgrade to Pro for unlimited scans."
                ),
            )

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
    # Phase 9 v4 — caller picks the match-analysis engine. "llm" runs the
    # regex + an LLM refinement pass (Groq → Anthropic; falls back to
    # regex when no provider or any failure). "regex" skips the LLM
    # entirely — fast + deterministic + no upstream dependency, at the
    # cost of being fooled by decorative degree mentions on unusual CV
    # layouts. Anything else falls through to regex (safe default).
    requested_engine = match_engine if match_engine in ("regex", "llm") else "regex"
    match = analyze_match(text, engine=requested_engine)

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
            match_engine=match.match_engine,
        ),
    )

    # Persistence is best-effort AND requires an authenticated caller (Phase 4).
    # Anonymous callers always get the in-memory result without a scan_id, so
    # nothing reaches the database without a known owner. The `persist` flag
    # was removed in Phase 7.7 — it had become a query parameter that let a
    # signed-in Free user dodge the quota counter via /scan-cv?persist=false.
    # Storage caps prevent one authed user from rapidly filling the table.
    if db is not None and current_user is not None:
        try:
            row = Scan(
                user_id=current_user,
                org_id=current_org,  # None for solo users, the active org id otherwise
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
    request: Request,
    file: UploadFile = File(...),
    db: Session | None = Depends(get_db),
    current_user: str | None = Depends(get_current_user_optional),
    current_org: str | None = Depends(get_current_org_optional),
) -> Response:
    """Re-scan the CV and return a Trust Report PDF."""
    # Pass db + current_user + current_org + request explicitly: when this
    # endpoint calls scan_cv as a regular Python function the FastAPI Depends
    # machinery does not fire, so the defaults would be the Depends marker
    # rather than real values. Phase 7.7: persist=False was removed so
    # /trust-report counts toward the free-tier quota. Phase 8.2: scan_cv's
    # rate-limit gate fires on the inner call too — /trust-report inherits
    # the limiter via the shared scan_cv call.
    scan = await scan_cv(
        request,
        file,
        db=db,
        current_user=current_user,
        current_org=current_org,
    )
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


@app.get("/scans", response_model=ScanListResponse)
def list_scans(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ScanListResponse:
    """List the scans the caller can see, newest first. Auth + DB required.

    Scope (Phase 5): when the caller is acting inside an organisation context,
    the list includes every scan whose user_id == current_user OR
    org_id == current_org. Without an org context, just the caller's own scans.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    q = db.query(Scan)
    if current_org:
        q = q.filter(
            or_(Scan.user_id == current_user, Scan.org_id == current_org)
        )
    else:
        q = q.filter(Scan.user_id == current_user)
    rows = q.order_by(Scan.created_at.desc()).all()
    scans = [
        ScanSummary(
            scan_id=str(row.id),
            created_at=row.created_at.isoformat(),
            filename=row.filename,
            risk_level=row.risk_level,
            risk_score=row.risk_score,
        )
        for row in rows
    ]
    return ScanListResponse(scans=scans, count=len(scans))


@app.get("/scans/{scan_id}", response_model=ScanResult)
def get_scan(
    scan_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ScanResult:
    """Return one scan's full detail by id. Auth + DB required.

    Scope (Phase 5): same rule as list_scans — the row is returned only when
    user_id == current_user OR (in an org context) org_id == current_org. A
    UUID belonging to another user/org returns 404, not 200, so the response
    never leaks that the scan exists.

    The raw original_text is never persisted (Phase 3 privacy invariant), so
    the scrubbed safe copy is echoed into original_text here. The stored
    injection / PII findings are intact, so the Risk evidence rehydrates
    fully; only the side-by-side raw-original pane shows the safe copy.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    q = db.query(Scan).filter(Scan.id == scan_id)
    if current_org:
        q = q.filter(or_(Scan.user_id == current_user, Scan.org_id == current_org))
    else:
        q = q.filter(Scan.user_id == current_user)
    row = q.first()
    if row is None:
        raise HTTPException(status_code=404, detail="Scan not found.")
    return ScanResult(
        scan_id=str(row.id),
        filename=row.filename,
        risk_level=row.risk_level,
        risk_score=row.risk_score,
        prompt_injection_findings=row.prompt_injection_findings or [],
        pii_findings=row.pii_findings or [],
        ai_text_likelihood=row.ai_text_likelihood,
        ai_text_score=row.ai_text_score,
        original_text=row.safe_copy_text,
        safe_copy_text=row.safe_copy_text,
        summary=row.summary,
        match_analysis=row.match_analysis,
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
        coverage_note=result.coverage_note,
    )


@app.post("/assessment", response_model=AssessmentReportModel)
def assessment_endpoint(
    req: AssessmentRequest,
    request: Request,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> AssessmentReportModel:
    """Generate a structured ProofHire v1 candidate assessment.

    Auth REQUIRED (Phase 7.7): anonymous → 401/503. Assessment is a Pro
    feature, and previously an anonymous-allowed cv_text branch let a denied
    Free user retry without the Authorization header and bypass the paywall.
    The demo path is preserved by leaving /scan-cv open to anonymous callers;
    Assessment is the upgrade carrot, not the demo headline.

    Input modes:
    - `scan_id`: loads the caller's own Scan row (filtered by user_id so a
      known UUID belonging to another user returns 404, not 200), reuses its
      safe_copy_text + signals, persists the Assessment.
    - `cv_text`: re-runs Phase-1 in memory, generates, does NOT persist
      (per-user history requires scan_id).
    Requires ANTHROPIC_API_KEY or GROQ_API_KEY on the server; returns 503 otherwise.
    """
    # Phase 8.6 — push identity into the log context.
    _push_request_context(user_id=current_user, org_id=current_org or "")

    # Phase 8.2 — rate limit (free=100/min, pro=300/min by user_id) ahead of
    # the Pro gate so a Pro user under attack still gets fast 429 rejection
    # before we pay any LLM cost on the upstream.
    _enforce_rate("/assessment", request, current_user, db)

    # Phase 9 demo-access policy (supersedes the Phase 7.3 + 7.7 Pro gate):
    # /assessment is open to ANY authenticated caller. The auth dep above
    # still raises 401/503 for anonymous callers, so the public demo path
    # still requires sign-in. Free signed-in callers are metered separately
    # from /scan-cv (cheap, no LLM) — assessments are LLM-backed and capped
    # at FREE_ASSESSMENT_LIMIT/month. Pro (personal or org) is unlimited.
    # DB-unconfigured deployments degrade open (Phase 4/5 invariant).
    if db is not None and not consume_assessment_or_refuse(
        current_user, current_org, db
    ):
        raise HTTPException(
            status_code=402,
            detail=(
                f"Free assessment limit reached ({FREE_ASSESSMENT_LIMIT}/month)."
                " Upgrade to Pro for unlimited assessments."
            ),
        )

    if req.scan_id:
        if db is None:
            raise HTTPException(
                status_code=503,
                detail="scan_id requires a configured database.",
            )
        # Scope by user_id (always) OR org_id (when the caller is in an org).
        # A scan tagged with a different user AND a different/no org returns
        # 404 rather than 200 — no leakage that the UUID exists.
        q = db.query(Scan).filter(Scan.id == req.scan_id)
        if current_org:
            q = q.filter(
                or_(Scan.user_id == current_user, Scan.org_id == current_org)
            )
        else:
            q = q.filter(Scan.user_id == current_user)
        scan_row = q.first()
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
    # ephemeral. user_id is the assessment creator; org_id is INHERITED from
    # the scan (not the caller's current org) so an Assessment cannot be
    # silently moved between orgs if the user switches Clerk org context.
    if req.scan_id and db is not None and current_user is not None:
        try:
            row = Assessment(
                scan_id=req.scan_id,
                user_id=current_user,
                org_id=scan_row.org_id,
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


# ── Phase 9 — recruiter co-pilot follow-up ──────────────────────────────────
# A separate, stricter rate limit than the route's identity-tier default —
# follow-ups are conversational and a runaway loop would burn LLM budget fast.
_FOLLOWUP_PER_MIN = 5


@app.post("/assessment/followup", response_model=FollowupResponse)
def assessment_followup_endpoint(
    req: FollowupRequest,
    request: Request,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> FollowupResponse:
    """Plain-prose follow-up answer to one question about a saved scan.

    Auth REQUIRED (anonymous → 401/503 from the dep). Pro REQUIRED — the
    answer is grounded in the candidate's signals + safe-copy CV, both
    loaded SERVER-side from the scan row by `scan_id`. The question text
    is the ONLY user-supplied content; signals and CV are never accepted
    from the body. Rate-limited to 5/min per user — follow-ups are
    conversational and a loop would burn upstream tokens.

    404 when the scan_id is unknown OR belongs to a different user / org
    (Phase 5 + 8.3 scope) — same "never leak existence" pattern as
    `/assessment` scan_id and `/scans/{id}`.
    """
    _push_request_context(user_id=current_user, org_id=current_org or "")

    # Per-user 5/min cap. The default /assessment limit (free=100 / pro=300)
    # is too high for a chatty endpoint; we override with a tight bucket
    # keyed by the verified Clerk user_id so dropping auth cannot rotate
    # identities.
    allowed, retry_after = check_rate(
        "/assessment/followup",
        f"user:{current_user}",
        per_min=_FOLLOWUP_PER_MIN,
    )
    if not allowed:
        raise HTTPException(
            status_code=429,
            detail="Too many follow-up questions. Please slow down.",
            headers={"Retry-After": str(int(retry_after) + 1)},
        )

    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")

    if not is_pro_for(current_user, current_org, db):
        raise HTTPException(
            status_code=402,
            detail="Follow-up questions require a Pro subscription.",
        )

    # Same scope as /assessment scan_id and /scans/{id}: caller's own scan
    # OR (in an org context) a scan tagged with that org. Out-of-scope →
    # 404, never 200 or 403.
    q = db.query(Scan).filter(Scan.id == req.scan_id)
    if current_org:
        q = q.filter(or_(Scan.user_id == current_user, Scan.org_id == current_org))
    else:
        q = q.filter(Scan.user_id == current_user)
    scan_row = q.first()
    if scan_row is None:
        raise HTTPException(status_code=404, detail="Scan not found.")

    # Build signals SERVER-side from the persisted row — never from req.
    cv_safe_copy = scan_row.safe_copy_text
    signals = {
        "risk_level": scan_row.risk_level,
        "risk_score": scan_row.risk_score,
        "injection_count": len(scan_row.prompt_injection_findings or []),
        "ai_text_likelihood": scan_row.ai_text_likelihood,
        "match": scan_row.match_analysis,
    }
    # End the read txn before the slow LLM call so we don't pin a pooled
    # connection while waiting on Anthropic / Groq.
    db.commit()

    try:
        answer = generate_followup_answer(
            question=req.question,
            signals=signals,
            cv_safe_copy=cv_safe_copy,
        )
    except AssessmentError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    return FollowupResponse(answer=answer)


@app.post("/billing/checkout-session", response_model=BillingRedirectResponse)
def billing_checkout_session(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
    current_org_role: str | None = Depends(get_current_org_role_optional),
    scope: str = "user",
) -> BillingRedirectResponse:
    """Start a Pro subscription. Returns a Stripe Checkout URL for the client to open.

    Auth + DB required. Redirect URLs are SERVER-configured (never client-supplied)
    to avoid an open-redirect. When `scope=org` the caller must be acting inside
    a Clerk organisation context AND have `org_role=admin` — viewers see 403.
    An already-Pro target (user or org) gets 409 and is pointed at the billing
    portal so we never start a second, duplicate subscription. Customer ids are
    reused per scope (user → `subscriptions`, org → `org_subscriptions`).
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    if not is_billing_configured():
        raise HTTPException(status_code=503, detail="Billing is not configured.")
    if scope not in ("user", "org"):
        raise HTTPException(status_code=422, detail="Unknown checkout scope.")

    if scope == "org":
        if not current_org:
            raise HTTPException(
                status_code=400,
                detail="Org checkout requires an active organisation context.",
            )
        if current_org_role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only an org admin can start an org subscription.",
            )
        if is_org_pro(current_org, db):
            raise HTTPException(
                status_code=409,
                detail="Org already subscribed to Pro. Use the org billing portal to manage.",
            )
        existing = (
            db.query(OrganizationSubscription)
            .filter(OrganizationSubscription.org_id == current_org)
            .first()
        )
        customer_id = existing.stripe_customer_id if existing else None
        try:
            url = create_checkout_session(
                user_id=current_user,
                customer_id=customer_id,
                scope="org",
                org_id=current_org,
            )
        except BillingError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        return BillingRedirectResponse(url=url)

    if is_pro(current_user, db):
        raise HTTPException(
            status_code=409,
            detail="Already subscribed to Pro. Use the billing portal to manage your plan.",
        )
    existing = (
        db.query(Subscription).filter(Subscription.user_id == current_user).first()
    )
    customer_id = existing.stripe_customer_id if existing else None
    try:
        url = create_checkout_session(
            user_id=current_user, customer_id=customer_id, scope="user"
        )
    except BillingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return BillingRedirectResponse(url=url)


@app.post("/billing/portal", response_model=BillingRedirectResponse)
def billing_portal(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
    current_org_role: str | None = Depends(get_current_org_role_optional),
    scope: str = "user",
) -> BillingRedirectResponse:
    """Open the Stripe Billing Portal so the caller can manage / cancel Pro.

    Auth + DB required. `scope=org` requires Clerk org context AND org_role=admin
    (non-admins get 403 — they don't manage the firm's billing). 404 when no
    Stripe customer exists for the scope yet.
    """
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    if not is_billing_configured():
        raise HTTPException(status_code=503, detail="Billing is not configured.")
    if scope not in ("user", "org"):
        raise HTTPException(status_code=422, detail="Unknown portal scope.")

    if scope == "org":
        if not current_org:
            raise HTTPException(
                status_code=400,
                detail="Org portal requires an active organisation context.",
            )
        if current_org_role != "admin":
            raise HTTPException(
                status_code=403,
                detail="Only an org admin can open the org billing portal.",
            )
        sub = (
            db.query(OrganizationSubscription)
            .filter(OrganizationSubscription.org_id == current_org)
            .first()
        )
    else:
        sub = (
            db.query(Subscription)
            .filter(Subscription.user_id == current_user)
            .first()
        )
    if sub is None or not sub.stripe_customer_id:
        raise HTTPException(status_code=404, detail="No billing account found.")
    try:
        url = create_portal_session(customer_id=sub.stripe_customer_id)
    except BillingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    return BillingRedirectResponse(url=url)


@app.get("/billing/status", response_model=BillingStatusResponse)
def billing_status(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> BillingStatusResponse:
    """Report the caller's plan, Pro flag, and this-month scan usage. Auth + DB
    required. Drives the frontend quota meter and Pro gating. No Stripe call —
    everything is read from our own rows, so it stays fast and works even if
    Stripe is unreachable.

    Phase 8.3 — `via_org` is True when the caller's effective Pro comes from
    the org's subscription, not from a personal sub. The personal `status`
    and `current_period_end` still come from the user's own row; the org's
    period and status are managed by the admin and shown in their UI."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    personal_pro = is_pro(current_user, db)
    org_pro = bool(current_org) and is_org_pro(current_org, db)
    pro = personal_pro or org_pro
    # Phase 8.1: read the gate-authoritative counter so the UI shows what
    # /scan-cv will actually enforce. Pre-8.1 free users with Scan rows but
    # no MonthlyUsage row see 0 until their next scan (deploy-day reset).
    used = quota_used_this_month(current_user, db)
    # Phase 9 — separate assessment counter (Free cap 5/month, Pro unlimited).
    asst_used = assessments_used_this_month(current_user, db)
    sub = db.query(Subscription).filter(Subscription.user_id == current_user).first()
    period_end = (
        sub.current_period_end.isoformat()
        if sub is not None and sub.current_period_end is not None
        else None
    )
    return BillingStatusResponse(
        plan="pro" if pro else "free",
        is_pro=pro,
        scans_used=used,
        scan_limit=FREE_SCAN_LIMIT,
        assessments_used=asst_used,
        assessment_limit=FREE_ASSESSMENT_LIMIT,
        current_period_end=period_end,
        status=sub.status if sub is not None else None,
        via_org=org_pro and not personal_pro,
    )


# ── Phase 7.5: Stripe webhook ────────────────────────────────────
# Runs server-to-server from Stripe (no Clerk JWT) — verify_and_parse_event is
# the authentication. Handlers UPSERT the per-user Subscription row with absolute
# values, so re-applying a change is harmless; the webhook_events ledger also
# short-circuits any event id already processed.
_SUBSCRIPTION_EVENTS = {
    "customer.subscription.created",
    "customer.subscription.updated",
    "customer.subscription.deleted",
}


def _period_end_to_datetime(value: object) -> datetime | None:
    """Stripe sends current_period_end as a unix timestamp; store it tz-aware UTC.
    Returns None for a missing/garbage value rather than raising."""
    if value is None:
        return None
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _apply_subscription_event(
    db: Session, obj: dict, event_created_unix: object
) -> None:
    """Upsert the per-user or per-org Subscription row from a Stripe subscription object.

    Resolves the entity by the metadata stamped at Checkout (Phase 8.4):
    - `metadata.scope == "org"` → upsert into `org_subscriptions` keyed on
      `metadata.org_id`.
    - default ("user" or missing) → upsert into `subscriptions` keyed on
      `metadata.user_id`, with a fallback lookup by Stripe customer id for
      pre-8.4 subs whose metadata never carried `scope`.

    Phase 7.7 hardening (carries over per table):
    - MED #1: events whose `created` is older than this row's last_event_at
      are skipped, so a delayed `subscription.updated` cannot resurrect Pro
      after `subscription.deleted`.
    - MED #2: if metadata points at a different existing row than the
      customer id, refuse the write rather than cross-wire two accounts.

    An event we cannot map is ignored (logged) so Stripe still receives 2xx.
    """
    metadata = obj.get("metadata") or {}
    scope = metadata.get("scope", "user")
    if scope == "org":
        _upsert_org_subscription(db, obj, metadata, event_created_unix)
        return

    user_id = metadata.get("user_id")
    customer_id = obj.get("customer")
    status = obj.get("status")
    sub_id = obj.get("id")
    period_end = _period_end_to_datetime(obj.get("current_period_end"))

    sub = None
    if user_id:
        sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if sub is None and customer_id:
        sub = (
            db.query(Subscription)
            .filter(Subscription.stripe_customer_id == customer_id)
            .first()
        )
        if sub is not None:
            user_id = sub.user_id

    if not user_id or not customer_id or not status:
        logger.warning("Subscription webhook could not be mapped to a user; ignoring")
        return

    # MED #2 — customer-id collision under a different user. The metadata told
    # us user A, but customer B already belongs to user C. Refuse rather than
    # cross-wire two accounts.
    collision = (
        db.query(Subscription)
        .filter(
            Subscription.stripe_customer_id == customer_id,
            Subscription.user_id != user_id,
        )
        .first()
    )
    if collision is not None:
        logger.warning(
            "Webhook customer_id already mapped to a different user; refusing"
        )
        return

    # MED #1 — drop out-of-order events. Compare the Stripe event `created`
    # against the last event applied to THIS row.
    event_created = _period_end_to_datetime(event_created_unix)
    if sub is not None and sub.last_event_at is not None and event_created is not None:
        last = sub.last_event_at
        if last.tzinfo is None:
            # SQLite (tests) drops tzinfo on read; treat stored values as UTC.
            last = last.replace(tzinfo=timezone.utc)
        if event_created <= last:
            logger.info(
                "Skipping subscription event older than last applied for user %s",
                user_id,
            )
            return

    if sub is None:
        sub = Subscription(
            user_id=user_id, stripe_customer_id=customer_id, status=status
        )
        db.add(sub)
    sub.stripe_customer_id = customer_id
    if sub_id:
        sub.stripe_subscription_id = sub_id
    sub.status = status
    sub.current_period_end = period_end
    sub.plan = "pro"
    if event_created is not None:
        sub.last_event_at = event_created


def _upsert_org_subscription(
    db: Session, obj: dict, metadata: dict, event_created_unix: object
) -> None:
    """Org-scope subscription upsert. Mirrors _apply_subscription_event's
    per-user logic but keyed on org_id against org_subscriptions."""
    org_id = metadata.get("org_id")
    customer_id = obj.get("customer")
    status = obj.get("status")
    sub_id = obj.get("id")
    period_end = _period_end_to_datetime(obj.get("current_period_end"))

    sub = None
    if org_id:
        sub = (
            db.query(OrganizationSubscription)
            .filter(OrganizationSubscription.org_id == org_id)
            .first()
        )
    if sub is None and customer_id:
        sub = (
            db.query(OrganizationSubscription)
            .filter(OrganizationSubscription.stripe_customer_id == customer_id)
            .first()
        )
        if sub is not None:
            org_id = sub.org_id

    if not org_id or not customer_id or not status:
        logger.warning("Org subscription webhook could not be mapped; ignoring")
        return

    # MED #2 — customer-id collision under a different org.
    collision = (
        db.query(OrganizationSubscription)
        .filter(
            OrganizationSubscription.stripe_customer_id == customer_id,
            OrganizationSubscription.org_id != org_id,
        )
        .first()
    )
    if collision is not None:
        logger.warning(
            "Org webhook customer_id already mapped to a different org; refusing"
        )
        return

    # MED #1 — out-of-order rejection per row.
    event_created = _period_end_to_datetime(event_created_unix)
    if sub is not None and sub.last_event_at is not None and event_created is not None:
        last = sub.last_event_at
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        if event_created <= last:
            logger.info("Skipping org subscription event older than last applied for %s", org_id)
            return

    if sub is None:
        sub = OrganizationSubscription(
            org_id=org_id, stripe_customer_id=customer_id, status=status
        )
        db.add(sub)
    sub.stripe_customer_id = customer_id
    if sub_id:
        sub.stripe_subscription_id = sub_id
    sub.status = status
    sub.current_period_end = period_end
    sub.plan = "pro"
    if event_created is not None:
        sub.last_event_at = event_created


def _apply_checkout_completed(db: Session, obj: dict) -> None:
    """Capture the Stripe customer id from a completed Checkout Session so the
    billing portal works even before the first subscription event lands. Does not
    set an active status — that arrives via subscription events; a fresh row is
    parked as 'incomplete' (is_pro treats it as not Pro).

    Phase 8.5 — routes to org_subscriptions when metadata.scope=="org"."""
    metadata = obj.get("metadata") or {}
    scope = metadata.get("scope", "user")
    customer_id = obj.get("customer")
    sub_id = obj.get("subscription")
    if not customer_id:
        logger.warning("checkout.session.completed missing customer; ignoring")
        return

    if scope == "org":
        org_id = metadata.get("org_id")
        if not org_id:
            logger.warning("checkout.session.completed scope=org missing org_id; ignoring")
            return
        sub = (
            db.query(OrganizationSubscription)
            .filter(OrganizationSubscription.org_id == org_id)
            .first()
        )
        if sub is None:
            db.add(
                OrganizationSubscription(
                    org_id=org_id,
                    stripe_customer_id=customer_id,
                    stripe_subscription_id=sub_id,
                    status="incomplete",
                )
            )
        else:
            sub.stripe_customer_id = customer_id
            if sub_id:
                sub.stripe_subscription_id = sub_id
        return

    user_id = obj.get("client_reference_id") or metadata.get("user_id")
    if not user_id:
        logger.warning("checkout.session.completed missing user; ignoring")
        return
    sub = db.query(Subscription).filter(Subscription.user_id == user_id).first()
    if sub is None:
        db.add(
            Subscription(
                user_id=user_id,
                stripe_customer_id=customer_id,
                stripe_subscription_id=sub_id,
                status="incomplete",
            )
        )
    else:
        sub.stripe_customer_id = customer_id
        if sub_id:
            sub.stripe_subscription_id = sub_id


@app.post("/billing/webhook")
async def billing_webhook(
    request: Request,
    db: Session | None = Depends(get_db),
) -> dict:
    """Receive Stripe billing webhooks (Phase 7.5).

    UNAUTHENTICATED by design — the Stripe signature is the authentication, so
    there is no Clerk dependency. Verifies the signature over the raw body against
    STRIPE_WEBHOOK_SECRET, then idempotently applies subscription lifecycle
    changes. 400 → bad/forged signature (Stripe must not retry); 503 → webhook
    secret or DB unconfigured (Stripe should retry)."""
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    # Phase 8.2 — per-IP rate limit on the unauthenticated surface so a
    # bogus-signature flood gets 429'd before we read the body or run HMAC.
    _enforce_rate("/billing/webhook", request)
    # Phase 7.7 LOW #1: a much smaller webhook-specific cap (256 KB) than the
    # global 10 MB upload cap. Stripe events are kilobytes; anything larger is
    # a forged flood and we short-circuit before doing HMAC work.
    cl = request.headers.get("content-length")
    if cl is None or not cl.isdigit() or int(cl) > 256 * 1024:
        raise HTTPException(status_code=413, detail="Webhook body exceeds limit.")
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    try:
        event = verify_and_parse_event(payload, sig_header)
    except WebhookError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except BillingError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

    event_id = event.get("id")
    event_type = event.get("type")
    if not event_id or not event_type:
        raise HTTPException(status_code=400, detail="Malformed event.")

    already = (
        db.query(WebhookEvent).filter(WebhookEvent.event_id == event_id).first()
    )
    if already is not None:
        return {"received": True, "duplicate": True}

    obj = (event.get("data") or {}).get("object") or {}
    if event_type in _SUBSCRIPTION_EVENTS:
        _apply_subscription_event(db, obj, event.get("created"))
    elif event_type == "checkout.session.completed":
        _apply_checkout_completed(db, obj)

    db.add(WebhookEvent(event_id=event_id, event_type=event_type))
    try:
        db.commit()
    except IntegrityError:
        # Phase 7.7 LOW #1 — concurrent delivery of the same event_id beat us
        # to the insert. The other branch has applied (or is applying) the
        # same mutation, so this is a duplicate, not a server error. Reply
        # 2xx so Stripe stops retrying.
        db.rollback()
        return {"received": True, "duplicate": True}
    except SQLAlchemyError:
        db.rollback()
        logger.exception("Failed to record billing webhook")
        raise HTTPException(status_code=503, detail="Could not record event.")
    return {"received": True}


def _sanitise_filename(name: str) -> str:
    """Strip directory components and unsafe characters from a filename."""
    base = os.path.basename(name)
    safe = re.sub(r"[^\w.\-]", "_", base)
    return safe[:128] or "upload"
