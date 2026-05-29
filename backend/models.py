from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Literal


class PromptInjectionFinding(BaseModel):
    pattern_id: str
    matched_text: str
    context: str  # surrounding 60 chars for display


class PIIFinding(BaseModel):
    pii_type: str
    matched_text: str


class MatchAnalysisModel(BaseModel):
    skills: dict[str, list[str]]
    experience_tier: str
    years_experience: int | None
    education_level: str
    interview_probes: list[str]
    key_claims: list[str]
    total_skills_found: int


class ScanResult(BaseModel):
    filename: str
    risk_level: Literal["GREEN", "ORANGE", "RED"]
    risk_score: int = Field(ge=0, le=100)
    prompt_injection_findings: list[PromptInjectionFinding]
    pii_findings: list[PIIFinding]
    ai_text_likelihood: Literal["LIKELY", "POSSIBL