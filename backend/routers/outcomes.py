"""Placement outcomes + conversion funnel (platform Phase 9).

An outcome is a funnel event (interviewed / offered / hired / rejected /
withdrawn / placed) for a candidate on a job. Conversion metrics and client ROI
reporting are derived from these rows. Every op is tenant-scoped and verifies
both the candidate and the job belong to the caller.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import Candidate, Job, Outcome
from routers._common import tenant_scope
from routers.audit import record_audit

router = APIRouter(tags=["outcomes"])

VALID_TYPES = {"interviewed", "offered", "hired", "rejected", "withdrawn", "placed"}
# Types that count as a positive commercial result for ROI headline stats.
_PLACED_TYPES = {"hired", "placed"}


class OutcomeCreate(BaseModel):
    job_id: uuid.UUID
    type: str = Field(min_length=1, max_length=16)
    notes: Optional[str] = None


class OutcomeOut(BaseModel):
    id: str
    candidate_id: str
    job_id: str
    type: str
    notes: Optional[str]
    occurred_at: str


class FunnelOut(BaseModel):
    counts: dict[str, int]
    total: int
    placed: int


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


def _out(o: Outcome) -> OutcomeOut:
    return OutcomeOut(
        id=str(o.id),
        candidate_id=str(o.candidate_id),
        job_id=str(o.job_id),
        type=o.type,
        notes=o.notes,
        occurred_at=o.occurred_at.isoformat(),
    )


def _counts(rows) -> FunnelOut:
    counts: dict[str, int] = {t: 0 for t in VALID_TYPES}
    for t, n in rows:
        counts[t] = n
    return FunnelOut(
        counts=counts,
        total=sum(counts.values()),
        placed=sum(counts[t] for t in _PLACED_TYPES),
    )


@router.post(
    "/candidates/{candidate_id}/outcomes", response_model=OutcomeOut, status_code=201
)
def record_outcome(
    candidate_id: uuid.UUID,
    body: OutcomeCreate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> OutcomeOut:
    db = _require_db(db)
    if body.type not in VALID_TYPES:
        raise HTTPException(status_code=422, detail="Invalid outcome type.")

    cand = tenant_scope(
        db.query(Candidate).filter(Candidate.id == candidate_id),
        Candidate,
        current_user,
        current_org,
    ).first()
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    job = tenant_scope(
        db.query(Job).filter(Job.id == body.job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    outcome = Outcome(
        user_id=current_user,
        org_id=current_org,
        candidate_id=cand.id,
        job_id=job.id,
        type=body.type,
        notes=body.notes,
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(outcome)
    db.commit()
    db.refresh(outcome)

    try:
        record_audit(
            db,
            user_id=current_user,
            org_id=current_org,
            action="outcome.recorded",
            entity_type="candidate",
            entity_id=str(cand.id),
            summary=f"{cand.full_name} — {body.type} on '{job.title}'.",
        )
    except Exception:  # noqa: BLE001
        db.rollback()
    return _out(outcome)


@router.get(
    "/candidates/{candidate_id}/outcomes", response_model=list[OutcomeOut]
)
def list_candidate_outcomes(
    candidate_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> list[OutcomeOut]:
    db = _require_db(db)
    cand = tenant_scope(
        db.query(Candidate).filter(Candidate.id == candidate_id),
        Candidate,
        current_user,
        current_org,
    ).first()
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    rows = (
        db.query(Outcome)
        .filter(Outcome.candidate_id == candidate_id)
        .order_by(Outcome.occurred_at.desc())
        .all()
    )
    return [_out(o) for o in rows]


@router.get("/jobs/{job_id}/outcomes/funnel", response_model=FunnelOut)
def job_funnel(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> FunnelOut:
    db = _require_db(db)
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    rows = (
        db.query(Outcome.type, func.count(Outcome.id))
        .filter(Outcome.job_id == job_id)
        .group_by(Outcome.type)
        .all()
    )
    return _counts(rows)


@router.get("/outcomes/funnel", response_model=FunnelOut)
def tenant_funnel(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> FunnelOut:
    """Tenant-wide conversion funnel — powers the dashboard."""
    db = _require_db(db)
    rows = tenant_scope(
        db.query(Outcome.type, func.count(Outcome.id)),
        Outcome,
        current_user,
        current_org,
    ).group_by(Outcome.type).all()
    return _counts(rows)
