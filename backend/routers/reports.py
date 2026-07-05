"""Client shortlist reports (platform Phase 4).

A report is generated on demand from a job's current shortlist — there is no
stored report entity until a use case needs one. JSON for the in-app preview,
PDF for sending to a client.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from client_report import ReportCandidate, build_client_report
from db import get_db
from db_models import Job, ShortlistEntry
from routers._common import tenant_scope

router = APIRouter(tags=["reports"])


class ReportCandidateOut(BaseModel):
    id: str
    full_name: str
    headline: Optional[str]
    status: str
    risk_level: Optional[str]
    risk_score: Optional[int]


class ReportOut(BaseModel):
    job_id: str
    job_title: str
    client_name: Optional[str]
    candidates: list[ReportCandidateOut]


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


def _job_and_shortlist(db: Session, job_id, user: str, org: Optional[str]):
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, user, org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    entries = (
        db.query(ShortlistEntry)
        .filter(ShortlistEntry.job_id == job.id)
        .order_by(ShortlistEntry.created_at.desc())
        .all()
    )
    return job, [e.candidate for e in entries if e.candidate is not None]


@router.get("/jobs/{job_id}/report", response_model=ReportOut)
def get_report(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ReportOut:
    db = _require_db(db)
    job, candidates = _job_and_shortlist(db, job_id, current_user, current_org)
    return ReportOut(
        job_id=str(job.id),
        job_title=job.title,
        client_name=job.client_name,
        candidates=[
            ReportCandidateOut(
                id=str(c.id),
                full_name=c.full_name,
                headline=c.headline,
                status=c.status,
                risk_level=c.scan.risk_level if c.scan else None,
                risk_score=c.scan.risk_score if c.scan else None,
            )
            for c in candidates
        ],
    )


@router.get("/jobs/{job_id}/report.pdf")
def get_report_pdf(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> Response:
    db = _require_db(db)
    job, candidates = _job_and_shortlist(db, job_id, current_user, current_org)
    pdf = build_client_report(
        job_title=job.title,
        client_name=job.client_name,
        candidates=[
            ReportCandidate(
                full_name=c.full_name,
                headline=c.headline,
                status=c.status,
                risk_level=c.scan.risk_level if c.scan else None,
                risk_score=c.scan.risk_score if c.scan else None,
            )
            for c in candidates
        ],
    )
    safe_title = "".join(ch for ch in job.title if ch.isalnum() or ch in " -_")[:60]
    return Response(
        content=pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="shortlist-{safe_title}.pdf"'
        },
    )
