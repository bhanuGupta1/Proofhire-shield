"""Generic candidate / job import — parsing, validation, dedupe (Phase 8).

Pure functions, no DB and no vendor coupling: the router hands us raw dict rows
(the frontend parses CSV/JSON into them) plus the set of keys already in the
tenant's data, and we return what to create vs skip. Keeping this provider-
agnostic is deliberate — a specific ATS connector is a thin adapter that
produces these same rows, never a change to the core.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


def _s(value) -> Optional[str]:
    """Coerce a cell to a trimmed string, or None if empty."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def clean_candidate(row: dict) -> Optional[dict]:
    """Normalise a raw candidate row. Accepts common header aliases. Returns
    None when there's no usable name (a candidate must have one)."""
    name = _s(row.get("full_name") or row.get("name") or row.get("candidate"))
    if not name:
        return None
    return {
        "full_name": name[:256],
        "email": _s(row.get("email")),
        "phone": _s(row.get("phone") or row.get("phone_number")),
        "headline": _s(row.get("headline") or row.get("title") or row.get("role")),
        "location": _s(row.get("location") or row.get("city")),
    }


def clean_job(row: dict) -> Optional[dict]:
    """Normalise a raw job row. Returns None without a title."""
    title = _s(row.get("title") or row.get("job_title") or row.get("role"))
    if not title:
        return None
    skills_raw = row.get("required_skills") or row.get("skills") or ""
    if isinstance(skills_raw, list):
        skills = [s for s in (_s(x) for x in skills_raw) if s]
    else:
        skills = [s.strip() for s in str(skills_raw).split(",") if s.strip()]
    return {
        "title": title[:256],
        "client_name": _s(row.get("client_name") or row.get("client")),
        "location": _s(row.get("location")),
        "required_skills": skills,
    }


@dataclass
class ImportPlan:
    to_create: list[dict] = field(default_factory=list)
    skipped: int = 0
    invalid: int = 0


def plan_candidate_import(rows: list[dict], existing_emails: set[str]) -> ImportPlan:
    """Split raw rows into create-vs-skip. Dedupe is by lowercased email —
    against existing candidates AND within the batch. Rows without an email are
    always created (we can't tell them apart). Nameless rows are invalid."""
    plan = ImportPlan()
    seen = {e.lower() for e in existing_emails}
    for row in rows:
        cleaned = clean_candidate(row)
        if cleaned is None:
            plan.invalid += 1
            continue
        email = cleaned.get("email")
        if email:
            key = email.lower()
            if key in seen:
                plan.skipped += 1
                continue
            seen.add(key)
        plan.to_create.append(cleaned)
    return plan


def plan_job_import(rows: list[dict], existing_keys: set[tuple]) -> ImportPlan:
    """Dedupe jobs by (lowercased title, lowercased client)."""
    plan = ImportPlan()
    seen = set(existing_keys)
    for row in rows:
        cleaned = clean_job(row)
        if cleaned is None:
            plan.invalid += 1
            continue
        key = (
            cleaned["title"].lower(),
            (cleaned.get("client_name") or "").lower(),
        )
        if key in seen:
            plan.skipped += 1
            continue
        seen.add(key)
        plan.to_create.append(cleaned)
    return plan


def _demo() -> None:
    rows = [
        {"name": "Ada Lovelace", "email": "ADA@x.com", "role": "Engineer"},
        {"full_name": "Ada Again", "email": "ada@x.com"},  # dup email
        {"name": "No Email Person"},
        {"email": "noname@x.com"},  # invalid — no name
    ]
    plan = plan_candidate_import(rows, {"existing@x.com"})
    assert len(plan.to_create) == 2, plan.to_create
    assert plan.skipped == 1, plan.skipped
    assert plan.invalid == 1, plan.invalid
    assert plan.to_create[0]["headline"] == "Engineer"

    jobs = [
        {"title": "Backend Engineer", "client": "Acme", "skills": "python, go"},
        {"title": "backend engineer", "client": "acme"},  # dup key
    ]
    jplan = plan_job_import(jobs, set())
    assert len(jplan.to_create) == 1, jplan.to_create
    assert jplan.to_create[0]["required_skills"] == ["python", "go"]
    print("importer self-check OK")


if __name__ == "__main__":
    _demo()
