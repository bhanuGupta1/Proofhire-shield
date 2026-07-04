"""Candidate CRUD + promote-from-scan (platform Phase 1).

A candidate is the durable pipeline record for a person. The primary way one is
created is by *promoting a scan*: POST with a `scan_id` and the endpoint copies
the contact details the scan already surfaced (email / phone from the PII
findings, a headline from the match analysis) and links `scan_id` so the
security provenance is preserved. Candidates can also be created manually with
just a name.

Every query is tenant-scoped via `tenant_scope`; a candidate id belonging to
another user/org returns 404, never 200.
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
from db_models import Candidate, Scan
from routers._common import tenant_scope

router = APIRouter(prefix="/candidates", tags=["candidates"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class CandidateCreate(BaseModel):
    # Optional so a scan can be promoted without re-typing the name; when no
    # scan_id is given, full_name is required (validated in the handler).
    full_name: Optional[str] = Field(default=None, max_length=256)
    email: Optional[str] = Field(default=None, max_length=256)
    phone: Optional[str] = Field(default=None, max_length=64)
    headline: Optional[str] = Field(default=None, max_length=256)
    location: Optional[str] = Field(default=None, max_length=128)
    notes: Optional[str] = None
    tags: list[str] = Field(default_factory=list)
    scan_id: Optional[uuid.UUID] = None


class CandidateUpdate(BaseModel):
    full_name: Optional[str] = Field(default=None, max_length=256)
    email: Optional[str] = Field(default=None, max_length=256)
    phone: Optional[str] = Field(default=None, max_length=64)
    headline: Optional[str] = Field(default=None, max_length=256)
    location: Optional[str] = Field(default=None, max_length=128)
    status: Optional[str] = Field(default=None, max_length=24)
    notes: Optional[str] = None
    tags: Optional[list[str]] = None


class CandidateOut(BaseModel):
    id: str
    full_name: str
    email: Optional[str]
    phone: Optional[str]
    headline: Optional[str]
    location: Optional[str]
    source: str
    status: str
    notes: Optional[str]
    tags: list[str]
    scan_id: Optional[str]
    # Denormalised risk badge from the linked scan, when present — lets the
    # candidate list show a risk light without a second round-trip.
    risk_level: Optional[str] = None
    risk_score: Optional[int] = None
    created_at: str
    updated_at: str


class CandidateListOut(BaseModel):
    candidates: list[CandidateOut]
    count: int


# ── Helpers ──────────────────────────────────────────────────────────────────

def _first_pii(scan: Scan, pii_type: str) -> Optional[str]:
    for finding in scan.pii_findings or []:
        if finding.get("pii_type") == pii_type:
            return finding.get("matched_text")
    return None


def _headline_from_match(scan: Scan) -> Optional[str]:
    match = scan.match_analysis or {}
    tier = match.get("experience_tier")
    years = match.get("years_experience")
    if tier and years:
        return f"{tier} · {years} yrs experience"
    return tier or None


def _serialise(cand: Candidate) -> CandidateOut:
    scan = cand.scan
    return CandidateOut(
        id=str(cand.id),
        full_name=cand.full_name,
        email=cand.email,
        phone=cand.phone,
        headline=cand.headline,
        location=cand.location,
        source=cand.source,
        status=cand.status,
        notes=cand.notes,
        tags=cand.tags or [],
        scan_id=str(cand.scan_id) if cand.scan_id else None,
        risk_level=scan.risk_level if scan else None,
        risk_score=scan.risk_score if scan else None,
        created_at=cand.created_at.isoformat(),
        updated_at=cand.updated_at.isoformat(),
    )


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


# ── Endpoints ────────────────────────────────────────────────────────────────

@router.post("", response_model=CandidateOut, status_code=201)
def create_candidate(
    body: CandidateCreate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> CandidateOut:
    db = _require_db(db)

    full_name = body.full_name
    email = body.email
    phone = body.phone
    headline = body.headline
    source = "manual"
    scan_id = None

    if body.scan_id is not None:
        scan = tenant_scope(
            db.query(Scan).filter(Scan.id == body.scan_id),
            Scan,
            current_user,
            current_org,
        ).first()
        if scan is None:
            raise HTTPException(status_code=404, detail="Scan not found.")
        source = "scan"
        scan_id = scan.id
        # Fill any field the caller didn't override from what the scan surfaced.
        email = email or _first_pii(scan, "email")
        phone = phone or _first_pii(scan, "phone")
        headline = headline or _headline_from_match(scan)
        if not full_name:
            # Filename stem is a sane placeholder the recruiter can correct.
            stem = scan.filename.rsplit(".", 1)[0]
            full_name = stem or "Unnamed candidate"

    if not full_name:
        raise HTTPException(
            status_code=422,
            detail="full_name is required when no scan_id is provided.",
        )

    cand = Candidate(
        user_id=current_user,
        org_id=current_org,
        scan_id=scan_id,
        full_name=full_name[:256],
        email=email,
        phone=phone,
        headline=headline,
        location=body.location,
        source=source,
        notes=body.notes,
        tags=body.tags or [],
    )
    try:
        db.add(cand)
        db.commit()
        db.refresh(cand)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to save candidate.")
    return _serialise(cand)


@router.get("", response_model=CandidateListOut)
def list_candidates(
    status: Optional[str] = None,
    q: Optional[str] = None,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> CandidateListOut:
    db = _require_db(db)
    query = tenant_scope(db.query(Candidate), Candidate, current_user, current_org)
    if status:
        query = query.filter(Candidate.status == status)
    if q:
        query = query.filter(Candidate.full_name.ilike(f"%{q}%"))
    rows = query.order_by(Candidate.created_at.desc()).all()
    return CandidateListOut(
        candidates=[_serialise(c) for c in rows], count=len(rows)
    )


@router.get("/{candidate_id}", response_model=CandidateOut)
def get_candidate(
    candidate_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> CandidateOut:
    db = _require_db(db)
    cand = tenant_scope(
        db.query(Candidate).filter(Candidate.id == candidate_id),
        Candidate,
        current_user,
        current_org,
    ).first()
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    return _serialise(cand)


@router.patch("/{candidate_id}", response_model=CandidateOut)
def update_candidate(
    candidate_id: uuid.UUID,
    body: CandidateUpdate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> CandidateOut:
    db = _require_db(db)
    cand = tenant_scope(
        db.query(Candidate).filter(Candidate.id == candidate_id),
        Candidate,
        current_user,
        current_org,
    ).first()
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")

    fields = body.model_dump(exclude_unset=True)
    for key, value in fields.items():
        setattr(cand, key, value)
    try:
        db.commit()
        db.refresh(cand)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=500, detail="Failed to update candidate.")
    return _serialise(cand)


@router.delete("/{candidate_id}", status_code=204, response_model=None)
def delete_candidate(
    candidate_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> None:
    db = _require_db(db)
    cand = tenant_scope(
        db.query(Candidate).filter(Candidate.id == candidate_id),
        Candidate,
        current_user,
        current_org,
    ).first()
    if cand is None:
        raise HTTPException(status_code=404, detail="Candidate not found.")
    db.delete(cand)
    db.commit()
