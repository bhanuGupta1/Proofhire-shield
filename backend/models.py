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


class ScanResponse(BaseModel):
    ok: bool
    result: ScanResult | None = None
    error: str | None = None
