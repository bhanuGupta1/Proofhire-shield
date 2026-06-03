from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, model_validator
from typing import Literal


class PromptInjectionFinding(BaseModel):
    pattern_id: str
    matched_text: str
    context: str  # surrounding 60 chars for display


class PIIFinding(BaseModel):
    pii_type: str
    matched_text: str


class CompletenessResultModel(BaseModel):
    score: int = Field(ge=0, le=100)
    breakdown: dict[str, bool]


class MatchAnalysisModel(BaseModel):
    skills: dict[str, list[str]]
    experience_tier: str
    years_experience: int | None
    education_level: str
    interview_probes: list[str]
    key_claims: list[str]
    total_skills_found: int
    summary: str
    completeness: CompletenessResultModel
    red_flags: list[str]


class JDMatchResultModel(BaseModel):
    match_score: int = Field(ge=0, le=100)
    matched_skills: list[str]
    missing_skills: list[str]
    bonus_skills: list[str]
    # Phase 9 — human-readable explanation when score is bounded by JD
    # quality (sparse JD → capped at 60). Empty when the score is full-confidence.
    coverage_note: str = ""


class JDMatchRequest(BaseModel):
    cv_text: str = Field(min_length=1, max_length=20000)
    jd_text: str = Field(min_length=1, max_length=20000)


class AssessmentDimensionModel(BaseModel):
    name: str
    text: str
    bullets: list[str] = []


class AssessmentReportModel(BaseModel):
    framework: str
    headline: str
    dimensions: list[AssessmentDimensionModel]
    overall_recommendation: str
    overall_score: int = Field(ge=0, le=100)
    next_steps: list[str]


class ScanSummary(BaseModel):
    """Compact scan record for the per-user history list."""
    scan_id: str
    created_at: str  # ISO 8601
    filename: str
    risk_level: Literal["GREEN", "ORANGE", "RED"]
    risk_score: int


class ScanListResponse(BaseModel):
    scans: list[ScanSummary]
    count: int


class AssessmentRequest(BaseModel):
    """Phase 2 review note: the endpoint re-runs the scanner + heuristic engine
    on `cv_text` server-side. Clients no longer supply match_analysis or
    risk_signals — that would be a trust-the-client antipattern.

    Phase 3: either `cv_text` (current behaviour: re-scan in memory, do not
    persist) or `scan_id` (load the persisted Scan, generate, persist the
    resulting Assessment linked by FK). Exactly one of the two is required."""
    cv_text: str | None = Field(default=None, max_length=20000)
    scan_id: uuid.UUID | None = None
    role_context: str | None = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def exactly_one_input(self):
        # Reject BOTH-present as well as NEITHER-present. The two input modes are
        # mutually exclusive: scan_id means "load the saved scan and reuse it";
        # cv_text means "re-derive in memory". Sending both silently dropped
        # cv_text under the old "either" check, which weakened the API contract.
        if bool(self.cv_text) == bool(self.scan_id):
            raise ValueError("Provide exactly one of cv_text or scan_id.")
        return self


class ScanResult(BaseModel):
    # UUID string when /scan-cv persisted the scan to the database; None when
    # DATABASE_URL is unset and the API is running in stateless mode.
    scan_id: str | None = None
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


class BillingRedirectResponse(BaseModel):
    """A Stripe-hosted URL (Checkout or Billing Portal) for the client to open."""
    url: str


class BillingStatusResponse(BaseModel):
    """Drives the frontend quota meter + Pro gating. current_period_end and status
    are echoed from the user's Subscription row (null when they have none).

    Phase 8.3 — `via_org` is True iff the caller's effective Pro comes from an
    OrganizationSubscription on the active Clerk org, not from a personal sub.
    The frontend uses this to swap the "Manage billing" CTA for "Org billing
    managed by admin" when the user is a non-admin org member benefiting from
    a firm subscription."""
    plan: Literal["free", "pro"]
    is_pro: bool
    scans_used: int = Field(ge=0)
    scan_limit: int = Field(ge=0)
    current_period_end: str | None = None  # ISO 8601 — when the Pro period renews/ends
    status: str | None = None  # raw Stripe subscription status, for display
    via_org: bool = False  # Phase 8.3 — Pro inherited from the active org's subscription


class FollowupRequest(BaseModel):
    """Phase 9 — body for /assessment/followup. The scan to query is
    identified by `scan_id`; we NEVER trust signals or CV text from the
    client. `assessment_id` is reserved for a later "answer in the context
    of a specific assessment" mode and is unused in 9.1/9.2."""
    scan_id: uuid.UUID
    question: str = Field(min_length=1, max_length=500)
    assessment_id: uuid.UUID | None = None


class FollowupResponse(BaseModel):
    answer: str
