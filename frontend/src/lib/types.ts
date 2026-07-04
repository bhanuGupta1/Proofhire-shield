export interface PromptInjectionFinding {
  pattern_id: string
  matched_text: string
  context: string
}

export interface PIIFinding {
  pii_type: string
  matched_text: string
}

export type RiskLevel = 'GREEN' | 'ORANGE' | 'RED'
export type AILikelihood = 'LIKELY' | 'POSSIBLE' | 'UNLIKELY'

export interface CompletenessResult {
  score: number
  breakdown: Record<string, boolean>
}

export interface MatchAnalysis {
  skills: Record<string, string[]>
  experience_tier: string
  years_experience: number | null
  education_level: string
  interview_probes: string[]
  key_claims: string[]
  total_skills_found: number
  summary: string
  completeness: CompletenessResult
  red_flags: string[]
  // Phase 9 v4 — which engine actually produced education_level + tier.
  // "regex" = deterministic on-device; "llm" = LLM successfully refined.
  // Optional for back-compat with older API responses.
  match_engine?: 'regex' | 'llm'
}

export interface ScanResult {
  // UUID string when the backend persisted the scan (DATABASE_URL set), null otherwise.
  scan_id: string | null
  filename: string
  risk_level: RiskLevel
  risk_score: number
  prompt_injection_findings: PromptInjectionFinding[]
  pii_findings: PIIFinding[]
  ai_text_likelihood: AILikelihood
  ai_text_score: number
  original_text: string
  safe_copy_text: string
  summary: string
  match_analysis: MatchAnalysis
}

export interface ScanResponse {
  ok: boolean
  result: ScanResult | null
  error: string | null
}

export interface JDMatchResult {
  match_score: number
  matched_skills: string[]
  missing_skills: string[]
  bonus_skills: string[]
  // Phase 9 — explanation rendered under the score when sparse JDs cap it.
  coverage_note?: string
}

export interface AssessmentDimension {
  name: string
  text: string
  bullets: string[]
}

export interface AssessmentReport {
  framework: string
  headline: string
  dimensions: AssessmentDimension[]
  overall_recommendation: string
  overall_score: number
  next_steps: string[]
}

export interface ScanSummary {
  scan_id: string
  created_at: string
  filename: string
  risk_level: RiskLevel
  risk_score: number
}

export interface ScanListResponse {
  scans: ScanSummary[]
  count: number
}

export interface BillingStatus {
  plan: 'free' | 'pro'
  is_pro: boolean
  scans_used: number
  scan_limit: number
  // Phase 9 — separate Free-tier counter for /assessment runs (limit 5/month).
  // Pro callers see used=0 and the limit is informational only.
  assessments_used?: number
  assessment_limit?: number
  current_period_end: string | null
  status: string | null
  // Phase 8.3 — true when the caller's Pro comes from the active org's sub,
  // not from a personal subscription. Drives the "managed by admin" UI for
  // non-admin org members.
  via_org?: boolean
}

export type BillingScope = 'user' | 'org'

// Phase 9 v4 — recruiter-selectable match-analysis engine. "llm" is the
// context-aware path (Groq → Anthropic); "regex" is fast + deterministic
// + on-device. Frontend persists the choice per browser.
export type MatchEngine = 'llm' | 'regex'

// Phase 9 — recruiter co-pilot follow-up answer.
export interface FollowupResponse {
  answer: string
}

// ── Platform: candidates & jobs ──────────────────────────────────────────────

export interface Candidate {
  id: string
  full_name: string
  email: string | null
  phone: string | null
  headline: string | null
  location: string | null
  source: string
  status: string
  notes: string | null
  tags: string[]
  scan_id: string | null
  // Denormalised from the linked scan, when present.
  risk_level: RiskLevel | null
  risk_score: number | null
  created_at: string
  updated_at: string
}

export interface CandidateListResponse {
  candidates: Candidate[]
  count: number
}

// Fields a recruiter can send when creating a candidate. When scan_id is set
// the server fills name/email/phone/headline from the scan, so full_name is
// optional in that path.
export interface CandidateCreate {
  full_name?: string
  email?: string
  phone?: string
  headline?: string
  location?: string
  notes?: string
  tags?: string[]
  scan_id?: string
}

export interface CandidateUpdate {
  full_name?: string
  email?: string
  phone?: string
  headline?: string
  location?: string
  status?: string
  notes?: string
  tags?: string[]
}

export interface Job {
  id: string
  title: string
  client_name: string | null
  location: string | null
  employment_type: string | null
  seniority: string | null
  description: string
  required_skills: string[]
  status: string
  created_at: string
  updated_at: string
}

export interface JobListResponse {
  jobs: Job[]
  count: number
}

export interface JobCreate {
  title: string
  client_name?: string
  location?: string
  employment_type?: string
  seniority?: string
  description?: string
  required_skills?: string[]
}

export type JobUpdate = Partial<JobCreate> & { status?: string }
