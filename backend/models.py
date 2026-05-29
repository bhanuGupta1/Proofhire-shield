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


class JDMatchResultModel(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    bonus_skills: list[str]


class JDMatchRequest(BaseModel):
    cv_text: str = Field(min_length=1, max_length=20000)
    jd_text: str = Field(min_length=1, max_length=20000)


class ScanResult(BaseModel):
    filename: str
    risk_level: Literal["GREEN", "ORANGE", "RED"]
    risk_score: int = Field(ge=0, le=100)
    prompt_injection_findings: list[PromptInjectionFinding]
    pii_findings: list[PIIFinding]
    ai_text_likelihood: Literal["LIKELY", "POSSIBLE", "UNLIKELY"]
    ai_text_score: float = Field(ge=0.0, le=1.0)
    original_text: str
    safe_copy_text: str
    summary: str
    match_analysis: MatchAnalysisModel
    jd_match: JDMatchResultModel | None = None


class ScanResponse(BaseModel):
    ok: bool
    result: ScanResult | None = None
    error: str | None = None
