"""Candidate↔job matching + talent search (platform Phase 3).

Deterministic, offline scoring via `matching.py`. Auto-match ranks the caller's
candidates against one job's required skills; talent search ranks them against a
free-text query. Both are tenant-scoped and read the candidate's skills from the
linked scan's stored match analysis.
"""
from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import Candidate, Job
from matching import (
    candidate_skills,
    score_candidate_for_job,
    talent_search_score,
)
from routers._common import tenant_scope

router = APIRouter(tags=["matching"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class MatchCandidate(BaseModel):
    candidate_id: str
    full_name: str
    headline: Optional[str]
    risk_level: Optional[str]
    risk_score: Optional[int]
    score: int  # 0–100
    matched_skills: list[str]
    missing_skills: list[str]


class AutoMatchResponse(BaseModel):
    job_id: str
    required_skills: list[str]
    matches: list[MatchCandidate]


class TalentSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=200)


class TalentHit(BaseModel):
    candidate_id: str
    full_name: str
    headline: Optional[str]
    risk_level: Optional[str]
    risk_score: Optional[int]
    score: int  # 0–100


class TalentSearchResponse(BaseModel):
    query: str
    results: list[TalentHit]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


def _tenant_candidates(db: Session, user: str, org: Optional[str]) -> list[Candidate]:
    return tenant_scope(db.query(Candidate), Candidate, user, org).all()


def _skills_of(cand: Candidate) -> set[str]:
    return candidate_skills(cand.scan.match_analysis if cand.scan else None)


# ── Auto-match ───────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/auto-match", response_model=AutoMatchResponse)
def auto_match(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> AutoMatchResponse:
    db = _require_db(db)
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    required = job.required_skills or []
    matches: list[MatchCandidate] = []
    for cand in _tenant_candidates(db, current_user, current_org):
        result = score_candidate_for_job(required, _skills_of(cand))
        if result.score <= 0:
            continue  # only surface candidates with at least one matching skill
        scan = cand.scan
        matches.append(
            MatchCandidate(
                candidate_id=str(cand.id),
                full_name=cand.full_name,
                headline=cand.headline,
                risk_level=scan.risk_level if scan else None,
                risk_score=scan.risk_score if scan else None,
                score=round(result.score * 100),
                matched_skills=result.matched_skills,
                missing_skills=result.missing_skills,
            )
        )
    # Highest fit first, then more matched skills, then name for stability.
    matches.sort(
        key=lambda m: (-m.score, -len(m.matched_skills), m.full_name.lower())
    )
    return AutoMatchResponse(
        job_id=str(job.id), required_skills=required, matches=matches
    )


# ── Talent search ────────────────────────────────────────────────────────────

@router.post("/talent/search", response_model=TalentSearchResponse)
def talent_search(
    body: TalentSearchRequest,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> TalentSearchResponse:
    db = _require_db(db)
    hits: list[TalentHit] = []
    for cand in _tenant_candidates(db, current_user, current_org):
        score = talent_search_score(
            body.query, _skills_of(cand), cand.headline, cand.full_name
        )
        if score <= 0:
            continue
        scan = cand.scan
        hits.append(
            TalentHit(
                candidate_id=str(cand.id),
                full_name=cand.full_name,
                headline=cand.headline,
                risk_level=scan.risk_level if scan else None,
                risk_score=scan.risk_score if scan else None,
                score=round(score * 100),
            )
        )
    hits.sort(key=lambda h: (-h.score, h.full_name.lower()))
    return TalentSearchResponse(query=body.query, results=hits)
