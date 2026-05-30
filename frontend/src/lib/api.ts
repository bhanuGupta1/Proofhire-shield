import type { ScanResponse, JDMatchResult, AssessmentReport, ScanResult } from './types'

export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

export async function scanCV(file: File): Promise<ScanResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/scan-cv`, { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text()
    return { ok: false, result: null, error: text }
  }
  return res.json()
}

export function trustReportUrl(): string {
  return `${API_BASE}/trust-report`
}

export async function matchJD(cvText: string, jdText: string): Promise<JDMatchResult> {
  const res = await fetch(`${API_BASE}/match-jd`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ cv_text: cvText, jd_text: jdText }),
  })
  if (!res.ok) {
    throw new Error(`Match failed (${res.status})`)
  }
  return res.json()
}

export async function generateAssessment(
  result: ScanResult,
  roleContext?: string,
): Promise<AssessmentReport> {
  const body = {
    cv_text: result.safe_copy_text,
    match_analysis: result.match_analysis,
    risk_signals: {
      risk_level: result.risk_level,
      risk_score: result.risk_score,
      injection_count: result.prompt_injection_findings.length,
      ai_text_likelihood: result.ai_text_likelihood,
    },
    role_context: roleContext ?? null,
  }
  const res = await fetch(`${API_BASE}/assessment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    if (res.status === 503) {
      throw new Error('Assessment is not yet configured on the server (Claude API key missing).')
    }
    const text = await res.text()
    throw new Error(`Assessment failed (${res.status}): ${text}`)
  }
  return res.json()
}
