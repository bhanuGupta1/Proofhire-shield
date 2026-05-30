import type { ScanResponse, JDMatchResult } from './types'

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
