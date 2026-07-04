"""Client CRM + public shortlist share links (platform Phase 5).

Two surfaces:
- Authenticated, tenant-scoped client CRUD.
- Share links: an authenticated recruiter mints an unguessable token for a job;
  anyone with the token can GET that job's shortlist read-only, no login. The
  public endpoint is the ONLY unauthenticated route here — it returns just the
  shared job's shortlist (name / headline / status / CV risk; never contact
  details) and honours expiry + revocation.
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from auth import get_current_org_optional, get_current_user
from db import get_db
from db_models import Client, ClientShare, Job, ShortlistEntry
from routers._common import tenant_scope
from routers.audit import record_audit

router = APIRouter(tags=["clients"])


# ── Schemas ──────────────────────────────────────────────────────────────────

class ClientCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    contact_name: Optional[str] = Field(default=None, max_length=256)
    contact_email: Optional[str] = Field(default=None, max_length=256)
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=256)
    contact_name: Optional[str] = Field(default=None, max_length=256)
    contact_email: Optional[str] = Field(default=None, max_length=256)
    notes: Optional[str] = None


class ClientOut(BaseModel):
    id: str
    name: str
    contact_name: Optional[str]
    contact_email: Optional[str]
    notes: Optional[str]
    created_at: str
    updated_at: str


class ClientListOut(BaseModel):
    clients: list[ClientOut]
    count: int


class ShareCreate(BaseModel):
    label: Optional[str] = Field(default=None, max_length=128)
    expires_in_days: Optional[int] = Field(default=None, ge=1, le=365)


class ShareOut(BaseModel):
    id: str
    token: str
    path: str  # frontend route a recruiter can copy/send
    label: Optional[str]
    expires_at: Optional[str]
    created_at: str


class ShareListOut(BaseModel):
    shares: list[ShareOut]


class PublicShareCandidate(BaseModel):
    full_name: str
    headline: Optional[str]
    status: str
    risk_level: Optional[str]
    risk_score: Optional[int]


class PublicShareOut(BaseModel):
    job_title: str
    client_name: Optional[str]
    candidates: list[PublicShareCandidate]


# ── Helpers ──────────────────────────────────────────────────────────────────

def _require_db(db: Optional[Session]) -> Session:
    if db is None:
        raise HTTPException(status_code=503, detail="Database is not configured.")
    return db


def _client_out(c: Client) -> ClientOut:
    return ClientOut(
        id=str(c.id),
        name=c.name,
        contact_name=c.contact_name,
        contact_email=c.contact_email,
        notes=c.notes,
        created_at=c.created_at.isoformat(),
        updated_at=c.updated_at.isoformat(),
    )


def _share_out(s: ClientShare) -> ShareOut:
    return ShareOut(
        id=str(s.id),
        token=s.token,
        path=f"/s/{s.token}",
        label=s.label,
        expires_at=s.expires_at.isoformat() if s.expires_at else None,
        created_at=s.created_at.isoformat(),
    )


# ── Client CRUD ──────────────────────────────────────────────────────────────

@router.post("/clients", response_model=ClientOut, status_code=201)
def create_client(
    body: ClientCreate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ClientOut:
    db = _require_db(db)
    client = Client(
        user_id=current_user,
        org_id=current_org,
        name=body.name,
        contact_name=body.contact_name,
        contact_email=body.contact_email,
        notes=body.notes,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    return _client_out(client)


@router.get("/clients", response_model=ClientListOut)
def list_clients(
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ClientListOut:
    db = _require_db(db)
    rows = (
        tenant_scope(db.query(Client), Client, current_user, current_org)
        .order_by(Client.created_at.desc())
        .all()
    )
    return ClientListOut(clients=[_client_out(c) for c in rows], count=len(rows))


def _load_client(db: Session, client_id, user: str, org: Optional[str]) -> Client:
    c = tenant_scope(
        db.query(Client).filter(Client.id == client_id), Client, user, org
    ).first()
    if c is None:
        raise HTTPException(status_code=404, detail="Client not found.")
    return c


@router.get("/clients/{client_id}", response_model=ClientOut)
def get_client(
    client_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ClientOut:
    db = _require_db(db)
    return _client_out(_load_client(db, client_id, current_user, current_org))


@router.patch("/clients/{client_id}", response_model=ClientOut)
def update_client(
    client_id: uuid.UUID,
    body: ClientUpdate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ClientOut:
    db = _require_db(db)
    c = _load_client(db, client_id, current_user, current_org)
    for key, value in body.model_dump(exclude_unset=True).items():
        setattr(c, key, value)
    db.commit()
    db.refresh(c)
    return _client_out(c)


@router.delete("/clients/{client_id}", status_code=204, response_model=None)
def delete_client(
    client_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> None:
    db = _require_db(db)
    c = _load_client(db, client_id, current_user, current_org)
    db.delete(c)
    db.commit()


# ── Shares ───────────────────────────────────────────────────────────────────

@router.post("/jobs/{job_id}/share", response_model=ShareOut, status_code=201)
def create_share(
    job_id: uuid.UUID,
    body: ShareCreate,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ShareOut:
    db = _require_db(db)
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")

    expires_at = None
    if body.expires_in_days is not None:
        expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    share = ClientShare(
        user_id=current_user,
        org_id=current_org,
        job_id=job.id,
        token=secrets.token_urlsafe(32),
        label=body.label,
        expires_at=expires_at,
    )
    db.add(share)
    db.commit()
    db.refresh(share)

    # Phase 7 — sharing a shortlist externally is exactly the kind of action an
    # audit trail exists to record.
    try:
        record_audit(
            db,
            user_id=current_user,
            org_id=current_org,
            action="share.created",
            entity_type="job",
            entity_id=str(job.id),
            summary=f"Shortlist share link created for '{job.title}'.",
        )
    except Exception:  # noqa: BLE001 — never let audit break the primary action
        db.rollback()
    return _share_out(share)


@router.get("/jobs/{job_id}/shares", response_model=ShareListOut)
def list_shares(
    job_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> ShareListOut:
    db = _require_db(db)
    job = tenant_scope(
        db.query(Job).filter(Job.id == job_id), Job, current_user, current_org
    ).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found.")
    rows = (
        db.query(ClientShare)
        .filter(ClientShare.job_id == job.id)
        .order_by(ClientShare.created_at.desc())
        .all()
    )
    return ShareListOut(shares=[_share_out(s) for s in rows])


@router.delete("/shares/{share_id}", status_code=204, response_model=None)
def revoke_share(
    share_id: uuid.UUID,
    db: Session | None = Depends(get_db),
    current_user: str = Depends(get_current_user),
    current_org: str | None = Depends(get_current_org_optional),
) -> None:
    db = _require_db(db)
    share = tenant_scope(
        db.query(ClientShare).filter(ClientShare.id == share_id),
        ClientShare,
        current_user,
        current_org,
    ).first()
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found.")
    db.delete(share)
    db.commit()


# ── Public share view (NO AUTH) ──────────────────────────────────────────────

@router.get("/share/{token}", response_model=PublicShareOut)
def public_share(
    token: str,
    db: Session | None = Depends(get_db),
) -> PublicShareOut:
    """Read-only shortlist for a share token. Unauthenticated by design — the
    unguessable token is the authorization. Returns 404 for unknown, revoked,
    or expired tokens so nothing about the job leaks."""
    db = _require_db(db)
    share = db.query(ClientShare).filter(ClientShare.token == token).first()
    if share is None:
        raise HTTPException(status_code=404, detail="Share not found.")
    if share.expires_at is not None:
        # SQLite returns naive datetimes; Postgres returns aware. Treat a naive
        # value as UTC so the comparison never raises across backends.
        exp = share.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if exp < datetime.now(timezone.utc):
            raise HTTPException(
                status_code=404, detail="This share link has expired."
            )

    job = db.query(Job).filter(Job.id == share.job_id).first()
    if job is None:
        raise HTTPException(status_code=404, detail="Share not found.")

    entries = (
        db.query(ShortlistEntry)
        .filter(ShortlistEntry.job_id == job.id)
        .order_by(ShortlistEntry.created_at.desc())
        .all()
    )
    candidates = []
    for e in entries:
        c = e.candidate
        if c is None:
            continue
        candidates.append(
            PublicShareCandidate(
                full_name=c.full_name,
                headline=c.headline,
                status=c.status,
                risk_level=c.scan.risk_level if c.scan else None,
                risk_score=c.scan.risk_score if c.scan else None,
            )
        )
    return PublicShareOut(
        job_title=job.title, client_name=job.client_name, candidates=candidates
    )
