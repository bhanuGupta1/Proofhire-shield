"""Job / requisition CRUD (platform Phase 1).

A job is a role the recruiter is filling. Phase 1 is plain tenant-scoped CRUD;
the candidate↔job relationship (pipeline stages, shortlists, matching) arrives
in later phases as separate association tables. Every query is tenant-scoped
via `tenant_scope`, so a job id from another user/org returns 404.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import Job
from routers._common import tenant_scope

router = APIRouter(prefix="/jobs", tags=["jobs"])

_STATUSES = {"open", "on_hold", "closed", "filled"}


class JobCreate(BaseModel):
    title: str = Field(min_length=1, max_length=256)
    client_name: Optional[str] = Field(default=None, max_length=256)
    location: Optional[str] = Field(default=None, max_length=128)
    employment_type: Optional[str] = Field(default=None, max_length=32)
    seniority: Optional[str] = Field(default=None, max_length=32)
    description: str = ""
    required_skills: list[str] = Field(default_factory=list)


class JobUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=256)
    client_name: Optional[str] = Field(default=None, max_length=256)
    location: Optional[str] = Field(default=None, max_length=128)
    employment_type: Optional[str] = Field(default=None, max_length=32)
    seniority: Optional[str] = Field(default=None, max_length=32)
    description: Optional[str] = None
    required_skills: Optional[list[str]] = None
    status: Optional[str] = None


class JobOut(BaseModel):
    id: str
    title: str
    client_name: Optional[str]
    location: Optional[str]
    employment_type: Optional[str]
    seniority: Optional[str]
    description: str
    required_skills: list[str]
    status: str
    created_at: str
    updated_at: str


class JobListOut(BaseModel):
    jobs: list[JobOut]
    count: int


def _serialise(job: Job) -> JobOut:
    return JobOut(
        id=str(job.id),
        title=job.title,
        client_name=job.client_name,
        location=job.location,
        employment_type=job.employment_type,
        seniority=job.seniority,
        description=job.description or "",
        required_skills=job.required_skills or [],
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
    )


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


@router.post("", response_model=JobOut, status_code=201)
def create_job(
    body: JobCreate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> JobOut:
    db = _require_db(db)
    job = Job(
        user_id=current_user,
        org_id=current_org,
        title=body.title,
        client_name=body.client_name,
        location=body.location,
        employment_type=body.employment_type,
        seniority=body.seniority,
        description=body.description or "",
        required_skills=body.required_skills or [],
    )
    try:
        db.add(job)
        db.commit()
        db.refresh(job)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save job.")
    return _serialise(job)


@router.get("", response_model=JobListOut)
def list_jobs(
    status: Optional[str] = None,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> JobListOut:
    db = _require_db(db)
    query = tenant_scope(db.query(Job), Job, current_user, current_org)
    if status:
        query = query.filter(Job.status == status)
    rows = query.order_by(Job.created_at.desc()).all()
    return JobListOut(jobs=[_serialise(j) for j in rows], count=len(rows))


@router.get("/{job_id}", response_model=JobOut)
def get_job(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> JobOut:
    db = _require_db(db)
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    return _serialise(job)


@router.patch("/{job_id}", response_model=JobOut)
def update_job(
    job_id: uuid.UUID,
    body: JobUpdate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> JobOut:
    db = _require_db(db)
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields and fields["status"] not in _STATUSES:
        raise HTTPException(status_code=422, detail="Invalid job status.")
    for key, value in fields.items():
        setattr(job, key, value)
    try:
        db.commit()
        db.refresh(job)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update job.")
    return _serialise(job)


@router.delete("/{job_id}", status_code=204, response_model=None)
def delete_job(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> None:
    db = _require_db(db)
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    db.delete(job)
    db.commit()
