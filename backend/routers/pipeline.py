"""Hiring pipeline + shortlists (platform Phase 2).

A job owns an ordered set of pipeline stages; a placement puts a candidate at a
stage in that job's funnel; a shortlist entry stars a candidate for a job. The
board endpoint lazily seeds a default stage set the first time it's requested
for a job with none, so job creation stays untouched.

Every op re-verifies the job (and, where relevant, the candidate) belongs to
the caller's tenant before touching pipeline rows, so cross-tenant ids 404.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import Candidate, Job, Placement, PipelineStage, ShortlistEntry
from routers._common import tenant_scope

router = APIRouter(tags=["pipeline"])

DEFAULT_STAGES = ["Applied", "Screening", "Interview", "Offer", "Hired"]


# ── Schemas ──────────────────────────────────────────────────────────────────

class BoardCard(BaseModel):
    placement_id: str
    candidate_id: str
    full_name: str
    headline: Optional[str]
    status: str
    risk_level: Optional[str]
    risk_score: Optional[int]


class StageOut(BaseModel):
    id: str
    name: str
    position: int
    candidates: list[BoardCard]


class BoardOut(BaseModel):
    job_id: str
    stages: list[StageOut]


class StageCreate(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    position: Optional[int] = None


class StageUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=64)
    position: Optional[int] = None


class PlacementCreate(BaseModel):
    candidate_id: uuid.UUID
    stage_id: Optional[uuid.UUID] = None


class PlacementMove(BaseModel):
    stage_id: uuid.UUID


class ShortlistAdd(BaseModel):
    candidate_id: uuid.UUID


class CandidateCard(BaseModel):
    id: str
    full_name: str
    headline: Optional[str]
    status: str
    risk_level: Optional[str]
    risk_score: Optional[int]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


def _load_job(db: Session, job_id, user: str, org: Optional[str]) -> Job:
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, user, org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return job


def _load_candidate(db: Session, candidate_id, user: str, org: Optional[str]) -> Candidate:
    cand = tenant_scope(
        db.query(Candidate).filter(Candidate.id == candidate_id),
        Candidate,
        user,
        org,
    ).first()
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return cand


def _stages_for_job(db: Session, job: Job) -> list[PipelineStage]:
    stages = (
        db.query(PipelineStage)
        .filter(PipelineStage.job_id == job.id)
        .order_by(PipelineStage.position)
        .all()
    )
    if stages:
        return stages
    # Lazily seed defaults so every job has a usable board without touching
    # job creation.
    for i, name in enumerate(DEFAULT_STAGES):
        db.add(
            PipelineStage(
                user_id=job.user_id,
                org_id=job.org_id,
                job_id=job.id,
                name=name,
                position=i,
            )
        )
    db.commit()
    return (
        db.query(PipelineStage)
        .filter(PipelineStage.job_id == job.id)
        .order_by(PipelineStage.position)
        .all()
    )


def _card(placement: Placement) -> BoardCard:
    c = placement.candidate
    return BoardCard(
        placement_id=str(placement.id),
        candidate_id=str(c.id),
        full_name=c.full_name,
        headline=c.headline,
        status=c.status,
        risk_level=c.scan.risk_level if c.scan else None,
        risk_score=c.scan.risk_score if c.scan else None,
    )


# ── Board ────────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/pipeline", response_model=BoardOut)
def get_board(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> BoardOut:
    db = _require_db(db)
    job = _load_job(db, job_id, current_user, current_org)
    stages = _stages_for_job(db, job)
    first_stage_id = stages[0].id

    placements = (
        db.query(Placement).filter(Placement.job_id == job.id).all()
    )
    # Bucket placements by stage; a null-stage placement (its stage was deleted)
    # falls into the first stage so it never vanishes from the board.
    by_stage: dict[uuid.UUID, list[BoardCard]] = {s.id: [] for s in stages}
    for p in placements:
        target = p.stage_id if p.stage_id in by_stage else first_stage_id
        by_stage[target].append(_card(p))

    return BoardOut(
        job_id=str(job.id),
        stages=[
            StageOut(
                id=str(s.id),
                name=s.name,
                position=s.position,
                candidates=by_stage[s.id],
            )
            for s in stages
        ],
    )


# ── Stages ───────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/stages", response_model=StageOut, status_code=201)
def create_stage(
    job_id: uuid.UUID,
    body: StageCreate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> StageOut:
    db = _require_db(db)
    job = _load_job(db, job_id, current_user, current_org)
    if body.position is None:
        current_max = (
            db.query(PipelineStage)
            .filter(PipelineStage.job_id == job.id)
            .count()
        )
        position = current_max
    else:
        position = body.position
    stage = PipelineStage(
        user_id=job.user_id,
        org_id=job.org_id,
        job_id=job.id,
        name=body.name,
        position=position,
    )
    db.add(stage)
    db.commit()
    db.refresh(stage)
    return StageOut(
        id=str(stage.id), name=stage.name, position=stage.position, candidates=[]
    )


def _load_stage(db: Session, stage_id, user: str, org: Optional[str]) -> PipelineStage:
    stage = tenant_scope(
        db.query(PipelineStage).filter(PipelineStage.id == stage_id),
        PipelineStage,
        user,
        org,
    ).first()
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found.")
    return stage


@router.patch("/pipeline/stages/{stage_id}", response_model=StageOut)
def update_stage(
    stage_id: uuid.UUID,
    body: StageUpdate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> StageOut:
    db = _require_db(db)
    stage = _load_stage(db, stage_id, current_user, current_org)
    if body.name is not None:
        stage.name = body.name
    if body.position is not None:
        stage.position = body.position
    db.commit()
    db.refresh(stage)
    return StageOut(
        id=str(stage.id), name=stage.name, position=stage.position, candidates=[]
    )


@router.delete("/pipeline/stages/{stage_id}", status_code=204, response_model=None)
def delete_stage(
    stage_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> None:
    db = _require_db(db)
    stage = _load_stage(db, stage_id, current_user, current_org)
    siblings = (
        db.query(PipelineStage)
        .filter(
            PipelineStage.job_id == stage.job_id, PipelineStage.id != stage.id
        )
        .order_by(PipelineStage.position)
        .all()
    )
    if not siblings:
        # Keep at least one stage so the board stays usable.
        raise HTTPException(
            status_code=409, detail="Cannot delete the only stage in a pipeline."
        )
    # Reassign this stage's placements to the first remaining stage before
    # deleting, so no candidate falls out of the funnel.
    target = siblings[0]
    db.query(Placement).filter(Placement.stage_id == stage.id).update(
        {Placement.stage_id: target.id}
    )
    db.delete(stage)
    db.commit()


# ── Placements ───────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/placements", response_model=BoardCard, status_code=201)
def add_placement(
    job_id: uuid.UUID,
    body: PlacementCreate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> BoardCard:
    db = _require_db(db)
    job = _load_job(db, job_id, current_user, current_org)
    _load_candidate(db, body.candidate_id, current_user, current_org)

    existing = (
        db.query(Placement)
        .filter(
            Placement.job_id == job.id, Placement.candidate_id == body.candidate_id
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="Candidate already in this job's pipeline."
        )

    stages = _stages_for_job(db, job)
    if body.stage_id is not None:
        if not any(s.id == body.stage_id for s in stages):
            raise HTTPException(status_code=404, detail="Stage not found.")
        stage_id = body.stage_id
    else:
        stage_id = stages[0].id

    placement = Placement(
        user_id=current_user,
        org_id=current_org,
        job_id=job.id,
        candidate_id=body.candidate_id,
        stage_id=stage_id,
    )
    db.add(placement)
    try:
        db.commit()
    except IntegrityError:
        # Concurrent duplicate slipped past the check above — the unique
        # (job_id, candidate_id) constraint is the real guard. Return a
        # deterministic 409 instead of a 500.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Candidate already in this job's pipeline."
        )
    db.refresh(placement)
    return _card(placement)


def _load_placement(db: Session, placement_id, user: str, org: Optional[str]) -> Placement:
    placement = tenant_scope(
        db.query(Placement).filter(Placement.id == placement_id),
        Placement,
        user,
        org,
    ).first()
    if placement is None:
        raise HTTPException(status_code=404, detail="Placement not found.")
    return placement


@router.patch("/pipeline/placements/{placement_id}", response_model=BoardCard)
def move_placement(
    placement_id: uuid.UUID,
    body: PlacementMove,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> BoardCard:
    db = _require_db(db)
    placement = _load_placement(db, placement_id, current_user, current_org)
    # The target stage must belong to the same job.
    stage = (
        db.query(PipelineStage)
        .filter(
            PipelineStage.id == body.stage_id,
            PipelineStage.job_id == placement.job_id,
        )
        .first()
    )
    if stage is None:
        raise HTTPException(status_code=404, detail="Stage not found for this job.")
    placement.stage_id = stage.id
    db.commit()
    db.refresh(placement)
    return _card(placement)


@router.delete("/pipeline/placements/{placement_id}", status_code=204, response_model=None)
def remove_placement(
    placement_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> None:
    db = _require_db(db)
    placement = _load_placement(db, placement_id, current_user, current_org)
    db.delete(placement)
    db.commit()


# ── Shortlist ────────────────────────────────────────────────────────────────

@router.get("/jobs/{job_id}/shortlist", response_model=list[CandidateCard])
def get_shortlist(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> list[CandidateCard]:
    db = _require_db(db)
    job = _load_job(db, job_id, current_user, current_org)
    entries = (
        db.query(ShortlistEntry)
        .filter(ShortlistEntry.job_id == job.id)
        .order_by(ShortlistEntry.created_at.desc())
        .all()
    )
    cards: list[CandidateCard] = []
    for e in entries:
        c = e.candidate
        if c is None:
            continue
        cards.append(
            CandidateCard(
                id=str(c.id),
                full_name=c.full_name,
                headline=c.headline,
                status=c.status,
                risk_level=c.scan.risk_level if c.scan else None,
                risk_score=c.scan.risk_score if c.scan else None,
            )
        )
    return cards


@router.post("/jobs/{job_id}/shortlist", response_model=CandidateCard, status_code=201)
def add_to_shortlist(
    job_id: uuid.UUID,
    body: ShortlistAdd,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> CandidateCard:
    db = _require_db(db)
    job = _load_job(db, job_id, current_user, current_org)
    cand = _load_candidate(db, body.candidate_id, current_user, current_org)

    existing = (
        db.query(ShortlistEntry)
        .filter(
            ShortlistEntry.job_id == job.id,
            ShortlistEntry.candidate_id == cand.id,
        )
        .first()
    )
    if existing is not None:
        raise HTTPException(
            status_code=409, detail="Candidate already shortlisted for this job."
        )
    db.add(
        ShortlistEntry(
            user_id=current_user,
            org_id=current_org,
            job_id=job.id,
            candidate_id=cand.id,
        )
    )
    try:
        db.commit()
    except IntegrityError:
        # Concurrent duplicate — the unique (job_id, candidate_id) constraint
        # guards it; return 409 rather than 500.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Candidate already shortlisted for this job."
        )
    return CandidateCard(
        id=str(cand.id),
        full_name=cand.full_name,
        headline=cand.headline,
        status=cand.status,
        risk_level=cand.scan.risk_level if cand.scan else None,
        risk_score=cand.scan.risk_score if cand.scan else None,
    )


@router.delete(
    "/jobs/{job_id}/shortlist/{candidate_id}", status_code=204, response_model=None
)
def remove_from_shortlist(
    job_id: uuid.UUID,
    candidate_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> None:
    db = _require_db(db)
    job = _load_job(db, job_id, current_user, current_org)
    entry = (
        db.query(ShortlistEntry)
        .filter(
            ShortlistEntry.job_id == job.id,
            ShortlistEntry.candidate_id == candidate_id,
        )
        .first()
    )
    if entry is None:
        raise HTTPException(status_code=404, detail="Not on the shortlist.")
    db.delete(entry)
    db.commit()
