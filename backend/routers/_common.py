"""Shared helpers for feature routers."""
from __future__ import annotations

from typing import Optional

from sqlalchemy import or_
from sqlalchemy.orm import Query


def tenant_scope(query: Query, model, user_id: str, org_id: Optional[str]) -> Query:
    """Restrict `query` to rows the caller may see.

    Same rule the core scan endpoints use: inside an org context a row is
    visible when it belongs to the caller OR to the active org; otherwise only
    the caller's own rows. Applied to every list AND detail query so a row id
    belonging to another tenant returns 404 rather than leaking existence.
    """
    if org_id:
        return query.filter(or_(model.user_id == user_id, model.org_id == org_id))
    return query.filter(model.user_id == user_id)
