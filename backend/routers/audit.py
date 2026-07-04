"""Append-only audit trail (platform Phase 7).

`record_audit` is the write side, called from the routers that perform
consequential actions; GET /audit is the tenant-scoped read side. There is no
update or delete endpoint by design.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import AuditLog
from routers._common import tenant_scope

router = APIRouter(tags=["audit"])


def record_audit(
    db: Session,
    *,
    user_id: str,
    org_id: Optional[str],
    action: str,
    summary: str,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
) -> None:
    """Append one audit row and commit. Best-effort — callers guard so a log
    failure never breaks the primary action."""
    db.add(
        AuditLog(
            user_id=user_id,
            org_id=org_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            summary=summary,
        )
    )
    db.commit()


class AuditEntry(BaseModel):
    id: str
    action: str
    entity_type: Optional[str]
    entity_id: Optional[str]
    summary: str
    created_at: str


class AuditListOut(BaseModel):
    entries: list[AuditEntry]
    count: int


@router.get("/audit", response_model=AuditListOut)
def list_audit(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> AuditListOut:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    rows = (
        tenant_scope(db.query(AuditLog), AuditLog, current_user, current_org)
        .order_by(AuditLog.created_at.desc())
        .limit(200)
        .all()
    )
    return AuditListOut(
        entries=[
            AuditEntry(
                id=str(r.id),
                action=r.action,
                entity_type=r.entity_type,
                entity_id=r.entity_id,
                summary=r.summary,
                created_at=r.created_at.isoformat(),
            )
            for r in rows
        ],
        count=len(rows),
    )
