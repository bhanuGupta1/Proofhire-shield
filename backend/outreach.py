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


# Stages a candidate moves through, each with its own message intent. 'sourced'
# is the default first-touch (the original behaviour).
STAGES = ("sourced", "applied", "screened", "interview", "offer", "rejection")


def _stage_copy(
    stage: str, first: str, role_line: str, context: str
) -> tuple[str, str]:
    """(subject, body) for a given pipeline stage. Falls back to 'sourced'."""
    if stage == "applied":
        return (
            "Thanks for applying",
            f"Hi {first},\n\nThanks for applying for {role_line} — we've received "
            f"your application and it's with our team.{context}\n\nWe'll be in "
            "touch shortly with next steps.\n\nBest regards,\nThe hiring team",
        )
    if stage == "screened":
        return (
            "Next steps on your application",
            f"Hi {first},\n\nGreat news — after reviewing your application for "
            f"{role_line}, we'd like to move you forward.{context}\n\nAre you "
            "available for a short call this week to discuss the role in more "
            "detail?\n\nBest regards,\nThe hiring team",
        )
    if stage == "interview":
        return (
            "Interview invitation",
            f"Hi {first},\n\nWe enjoyed learning about your background and would "
            f"like to invite you to interview for {role_line}.{context}\n\nPlease "
            "let me know a few times that suit you and I'll get it scheduled.\n\n"
            "Best regards,\nThe hiring team",
        )
    if stage == "offer":
        return (
            "An offer for you",
            f"Hi {first},\n\nWe were really impressed throughout the process and "
            f"are delighted to move to an offer for {role_line}.{context}\n\nI'll "
            "follow up with the details — in the meantime, congratulations, and "
            "do reach out with any questions.\n\nBest regards,\nThe hiring team",
        )
    if stage == "rejection":
        return (
            "Update on your application",
            f"Hi {first},\n\nThank you for the time you invested in the process "
            f"for {role_line}. After careful consideration we won't be moving "
            "forward on this occasion.\n\nThis was a competitive process and we'd "
            "genuinely welcome you applying for future roles that fit your "
            "experience.\n\nBest regards,\nThe hiring team",
        )
    # 'sourced' / default first-touch.
    subject = "An opportunity that fits your profile"
    body = (
        f"Hi {first},\n\n"
        f"I came across your profile and wanted to reach out about {role_line}."
        f"{context}\n\n"
        "Would you be open to a short call this week to talk it through? "
        "Happy to work around your schedule.\n\n"
        "Best regards,\nThe hiring team"
    )
    return subject, body


def draft_outreach(
    full_name: str,
    headline: Optional[str] = None,
    job_title: Optional[str] = None,
    recruiter_name: Optional[str] = None,
    stage: str = "sourced",
) -> OutreachDraft:
    """A personalised, stage-aware outreach draft."""
    first = _first_name(full_name)
    role_line = (
        f"the {job_title} role" if job_title else "an opportunity I think fits well"
    )
    context = f" Your background in {headline.lower()} stood out." if headline else ""

    subject, body = _stage_copy(
        stage if stage in STAGES else "sourced", first, role_line, context
    )
    # A first-touch sourcing message that knows the job title reads better with
    # it in the subject.
    if stage in ("sourced",) and job_title:
        subject = f"{job_title} opportunity"
    if recruiter_name:
        body = body.replace("The hiring team", recruiter_name)
    return OutreachDraft(subject=subject, body=body)


def _demo() -> None:
    d = draft_outreach("Ada Lovelace", headline="Senior Data Engineer", job_title="Analytics Lead")
    assert "Hi Ada," in d.body, d.body
    assert d.subject == "Analytics Lead opportunity", d.subject
    assert "senior data engineer" in d.body.lower()
    d2 = draft_outreach("")
    assert "Hi there," in d2.body

    # Stage-aware drafts differ by stage.
    rej = draft_outreach("Ada Lovelace", stage="rejection")
    assert "won't be moving forward" in rej.body
    assert rej.subject == "Update on your application"
    offer = draft_outreach("Ada", job_title="Lead", stage="offer")
    assert "offer" in offer.body.lower()
    # Unknown stage falls back to the first-touch draft.
    assert "reach out" in draft_outreach("Ada", stage="bogus").body.lower()
    print("outreach self-check OK")


if __name__ == "__main__":
    _demo()
