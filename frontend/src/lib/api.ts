import type { ScanResponse } from './types'

export async function scanCV(file: File): Promise<ScanResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch('/scan-cv', { method: 'POST', body: form })
  if (!res.ok) {
    const text = await res.text()
    return { ok: false, result: null, error: text }
  }
  return res.json()
}

export function trustReportUrl(): string {
  return '/trust-report'
}
