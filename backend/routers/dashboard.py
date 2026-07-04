"""Recruiter dashboard + Today queue (platform Phase 4).

All metrics are derived on the fly from the existing candidate / job / scan /
pipeline tables — no separate analytics store until there's a reason for one.
Everything is tenant-scoped, so the numbers reflect exactly what the caller can
see.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import Candidate, Job, Placement, Scan, ShortlistEntry
from routers._common import tenant_scope

router = APIRouter(tags=["dashboard"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class RiskBreakdown(BaseModel):
    GREEN: int = 0
    ORANGE: int = 0
    RED: int = 0


class DashboardMetrics(BaseModel):
    candidates_total: int
    candidates_by_status: dict[str, int]
    jobs_total: int
    jobs_by_status: dict[str, int]
    open_jobs: int
    placements_total: int
    shortlist_total: int
    risk: RiskBreakdown


class MiniCandidate(BaseModel):
    id: str
    full_name: str
    headline: Optional[str]
    risk_level: Optional[str]


class MiniJob(BaseModel):
    id: str
    title: str


class TodayQueue(BaseModel):
    new_candidates: list[MiniCandidate]
    new_candidates_count: int
    high_risk_candidates: list[MiniCandidate]
    high_risk_count: int
    open_jobs_without_candidates: list[MiniJob]
    open_jobs_without_candidates_count: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


def _counts_by(db: Session, model, column, user: str, org: Optional[str]) -> dict[str, int]:
    q = tenant_scope(
        db.query(column, func.count(model.id)), model, user, org
    ).group_by(column)
    return {status: n for status, n in q.all()}


# ── Metrics ──────────────────────────────────────────────────────────────────

@router.get("/dashboard/metrics", response_model=DashboardMetrics)
def dashboard_metrics(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> DashboardMetrics:
    db = _require_db(db)

    cand_by_status = _counts_by(
        db, Candidate, Candidate.status, current_user, current_org
    )
    job_by_status = _counts_by(db, Job, Job.status, current_user, current_org)
    risk_counts = _counts_by(db, Scan, Scan.risk_level, current_user, current_org)

    placements_total = tenant_scope(
        db.query(Placement), Placement, current_user, current_org
    ).count()
    shortlist_total = tenant_scope(
        db.query(ShortlistEntry), ShortlistEntry, current_user, current_org
    ).count()

    return DashboardMetrics(
        candidates_total=sum(cand_by_status.values()),
        candidates_by_status=cand_by_status,
        jobs_total=sum(job_by_status.values()),
        jobs_by_status=job_by_status,
        open_jobs=job_by_status.get("open", 0),
        placements_total=placements_total,
        shortlist_total=shortlist_total,
        risk=RiskBreakdown(
            GREEN=risk_counts.get("GREEN", 0),
            ORANGE=risk_counts.get("ORANGE", 0),
            RED=risk_counts.get("RED", 0),
        ),
    )


# ── Today ────────────────────────────────────────────────────────────────────

@router.get("/today", response_model=TodayQueue)
def today(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> TodayQueue:
    db = _require_db(db)

    # Candidates awaiting first review.
    new_q = tenant_scope(
        db.query(Candidate).filter(Candidate.status == "new"),
        Candidate,
        current_user,
        current_org,
    )
    new_count = new_q.count()
    new_rows = new_q.order_by(Candidate.created_at.desc()).limit(10).all()

    # Candidates whose CV scanned high-risk — need a human look before use.
    risk_q = tenant_scope(
        db.query(Candidate).join(Scan, Candidate.scan_id == Scan.id).filter(
            Scan.risk_level == "RED"
        ),
        Candidate,
        current_user,
        current_org,
    )
    risk_count = risk_q.count()
    risk_rows = risk_q.order_by(Candidate.created_at.desc()).limit(10).all()

    # Open jobs with nobody in the pipeline yet.
    placed_job_ids = {
        row[0]
        for row in tenant_scope(
            db.query(Placement.job_id), Placement, current_user, current_org
        ).all()
    }
    open_jobs_q = tenant_scope(
        db.query(Job).filter(Job.status == "open"), Job, current_user, current_org
    )
    empty_open = [j for j in open_jobs_q.all() if j.id not in placed_job_ids]

    def _mini_c(c: Candidate) -> MiniCandidate:
        return MiniCandidate(
            id=str(c.id),
            full_name=c.full_name,
            headline=c.headline,
            risk_level=c.scan.risk_level if c.scan else None,
        )

    return TodayQueue(
        new_candidates=[_mini_c(c) for c in new_rows],
        new_candidates_count=new_count,
        high_risk_candidates=[_mini_c(c) for c in risk_rows],
        high_risk_count=risk_count,
        open_jobs_without_candidates=[
            MiniJob(id=str(j.id), title=j.title) for j in empty_open[:10]
        ],
        open_jobs_without_candidates_count=len(empty_open),
    )
