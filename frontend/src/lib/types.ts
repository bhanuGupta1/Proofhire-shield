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
}

export interface ScanResponse {
  ok: boolean
  result: ScanResult | null
  error: string | null
}
