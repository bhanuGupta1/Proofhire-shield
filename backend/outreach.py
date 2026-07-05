"""Outreach draft generation (platform Phase 6).

Deterministic, offline template — no LLM dependency, so it works everywhere and
is trivially testable. The recruiter edits the draft before sending. Upgrade
path (localised to this function): call the assessment provider to rewrite the
body in the recruiter's voice, falling back to this template on any failure —
the same provider-optional pattern the match engine uses.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass
class OutreachDraft:
    subject: str
    body: str


def _first_name(full_name: str) -> str:
    parts = full_name.strip().split()
    return parts[0] if parts else "there"


def draft_outreach(
    full_name: str,
    headline: Optional[str] = None,
    job_title: Optional[str] = None,
    recruiter_name: Optional[str] = None,
) -> OutreachDraft:
    """A personalised first-touch outreach email draft."""
    first = _first_name(full_name)
    role_line = (
        f"a {job_title} role we're currently hiring for"
        if job_title
        else "an opportunity I think could be a strong fit"
    )
    context = f" Your background in {headline.lower()} stood out." if headline else ""
    sign_off = recruiter_name or "The hiring team"

    subject = (
        f"{job_title} opportunity" if job_title else "An opportunity that fits your profile"
    )
    body = (
        f"Hi {first},\n\n"
        f"I came across your profile and wanted to reach out about {role_line}."
        f"{context}\n\n"
        "Would you be open to a short call this week to talk it through? "
        "Happy to work around your schedule.\n\n"
        "Best regards,\n"
        f"{sign_off}"
    )
    return OutreachDraft(subject=subject, body=body)


def _demo() -> None:
    d = draft_outreach("Ada Lovelace", headline="Senior Data Engineer", job_title="Analytics Lead")
    assert "Hi Ada," in d.body, d.body
    assert d.subject == "Analytics Lead opportunity", d.subject
    assert "senior data engineer" in d.body.lower()
    d2 = draft_outreach("")
    assert "Hi there," in d2.body
    print("outreach self-check OK")


if __name__ == "__main__":
    _demo()
