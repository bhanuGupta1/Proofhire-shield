"""Generic candidate / job import (platform Phase 8).

Accepts JSON rows (the frontend parses CSV → rows), validates and dedupes them
via the pure `importer` module, then bulk-creates. No import-run table — the
action is audit-logged, which is the record that matters. A specific ATS
connector is just an adapter that produces these same rows.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import Candidate, Job
from importer import plan_candidate_import, plan_job_import
from routers._common import tenant_scope
from routers.audit import record_audit

router = APIRouter(tags=["import"])

# Cap a single import so one call can't try to insert a runaway batch.
_MAX_ROWS = 1000


class ImportRequest(BaseModel):
    rows: list[dict] = Field(default_factory=list)


class ImportResult(BaseModel):
    created: int
    skipped: int
    invalid: int


def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


def _check_size(rows: list[dict]) -> None:
    if len(rows) > _MAX_ROWS:
        raise HTTPException(
            status_code=413, detail=f"Too many rows (max {_MAX_ROWS} per import)."
        )


@router.post("/import/candidates", response_model=ImportResult)
def import_candidates(
    body: ImportRequest,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ImportResult:
    db = _require_db(db)
    _check_size(body.rows)

    existing_emails = {
        e
        for (e,) in tenant_scope(
            db.query(Candidate.email), Candidate, current_user, current_org
        ).all()
        if e
    }
    plan = plan_candidate_import(body.rows, existing_emails)

    for row in plan.to_create:
        db.add(
            Candidate(
                user_id=current_user,
                org_id=current_org,
                source="import",
                full_name=row["full_name"],
                email=row.get("email"),
                phone=row.get("phone"),
                headline=row.get("headline"),
                location=row.get("location"),
            )
        )
    db.commit()

    if plan.to_create:
        try:
            record_audit(
                db,
                user_id=current_user,
                org_id=current_org,
                action="candidates.imported",
                entity_type="candidate",
                summary=f"Imported {len(plan.to_create)} candidate(s).",
            )
        except Exception:  # noqa: BLE001
            db.rollback()

    return ImportResult(
        created=len(plan.to_create), skipped=plan.skipped, invalid=plan.invalid
    )


@router.post("/import/jobs", response_model=ImportResult)
def import_jobs(
    body: ImportRequest,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ImportResult:
    db = _require_db(db)
    _check_size(body.rows)

    existing_keys = {
        (title.lower(), (client or "").lower())
        for (title, client) in tenant_scope(
            db.query(Job.title, Job.client_name), Job, current_user, current_org
        ).all()
    }
    plan = plan_job_import(body.rows, existing_keys)

    for row in plan.to_create:
        db.add(
            Job(
                user_id=current_user,
                org_id=current_org,
                title=row["title"],
                client_name=row.get("client_name"),
                location=row.get("location"),
                required_skills=row.get("required_skills", []),
            )
        )
    db.commit()

    if plan.to_create:
        try:
            record_audit(
                db,
                user_id=current_user,
                org_id=current_org,
                action="jobs.imported",
                entity_type="job",
                summary=f"Imported {len(plan.to_create)} job(s).",
            )
        except Exception:  # noqa: BLE001
            db.rollback()

    return ImportResult(
        created=len(plan.to_create), skipped=plan.skipped, invalid=plan.invalid
    )
