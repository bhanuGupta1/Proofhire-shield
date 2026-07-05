"""Interview notes → red/green flag summary (platform Phase 10).

A stateless recruiter aid: paste ad-hoc interview notes, get back green flags,
red flags, and a recommended next step. Auth-gated (it's an internal tool) but
stores nothing — the summary is computed on the fly by the offline
`interview_flags` heuristic.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from auth import get_current_user
from interview_flags import summarize_notes

router = APIRouter(tags=["interview"])


class FlagsRequest(BaseModel):
    notes: str = Field(min_length=1, max_length=10000)


class FlagsResponse(BaseModel):
    green_flags: list[str]
    red_flags: list[str]
    recommended_step: str


@router.post("/interview/flags", response_model=FlagsResponse)
def interview_flags(
    body: FlagsRequest,
    current_user: str = Depends(get_current_user),
) -> FlagsResponse:
    summary = summarize_notes(body.notes)
    return FlagsResponse(
        green_flags=summary.green_flags,
        red_flags=summary.red_flags,
        recommended_step=summary.recommended_step,
    )
