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
}

export interface ScanResult {
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
}
