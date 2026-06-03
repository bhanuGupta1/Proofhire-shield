import type {
  AssessmentReport,
  BillingStatus,
  JDMatchResult,
  ScanListResponse,
  ScanResponse,
  ScanResult,
} from './types'

export const API_BASE: string =
  (import.meta.env.VITE_API_URL as string | undefined)?.replace(/\/$/, '') ?? ''

function bearer(token: string | null | undefined): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

// Pull a human-readable message out of an error response. FastAPI sends
// `{ "detail": "..." }`; fall back to the raw body, then the status code.
async function errorDetail(res: Response): Promise<string> {
  const raw = await res.text()
  try {
    const parsed = JSON.parse(raw)
    if (parsed && typeof parsed.detail === 'string') {
      return parsed.detail
    }
  } catch {
    // body wasn't JSON — use the raw text below
  }
  return raw || `Request failed (${res.status})`
}

export async function scanCV(file: File, token?: string | null): Promise<ScanResponse> {
  const form = new FormData()
  form.append('file', file)
  // Do not set Content-Type here — fetch + FormData generates the multipart
  // boundary header automatically; overriding it breaks the parse.
  const res = await fetch(`${API_BASE}/scan-cv`, {
    method: 'POST',
    headers: bearer(token),
    body: form,
  })
  if (!res.ok) {
    return { ok: false, result: null, error: await errorDetail(res) }
  }
  return res.json()
}

export function trustReportUrl(): string {
  return `${API_BASE}/trust-report`
}

export async function matchJD(
  cvText: string,
  jdText: string,
  token?: string | null,
): Promise<JDMatchResult> {
  const res = await fetch(`${API_BASE}/match-jd`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
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
  token?: string | null,
): Promise<AssessmentReport> {
  // Send the original text — the server re-runs the Phase-1 pipeline so its
  // structured signals come from authoritative server state, not from us.
  const body = {
    cv_text: result.original_text,
    role_context: roleContext ?? null,
  }
  const res = await fetch(`${API_BASE}/assessment`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    // Display whatever the backend says. Never hardcode provider names — the
    // server may be running on Anthropic, Groq/DeepSeek R1, or anything else.
    const raw = await res.text()
    let detail = raw
    try {
      const parsed = JSON.parse(raw)
      if (parsed && typeof parsed.detail === 'string') {
        detail = parsed.detail
      }
    } catch {
      // body wasn't JSON — use the raw text we already have
    }
    throw new Error(detail || `Request failed (${res.status})`)
  }
  return res.json()
}

export async function listScans(token: string): Promise<ScanListResponse> {
  const res = await fetch(`${API_BASE}/scans`, {
    method: 'GET',
    headers: bearer(token),
  })
  if (!res.ok) {
    throw new Error(`List scans failed (${res.status})`)
  }
  return res.json()
}

export async function getScan(scanId: string, token: string): Promise<ScanResult> {
  const res = await fetch(`${API_BASE}/scans/${scanId}`, {
    method: 'GET',
    headers: bearer(token),
  })
  if (!res.ok) {
    throw new Error(`Get scan failed (${res.status})`)
  }
  return res.json()
}

export async function getBillingStatus(token: string): Promise<BillingStatus> {
  const res = await fetch(`${API_BASE}/billing/status`, {
    method: 'GET',
    headers: bearer(token),
  })
  if (!res.ok) {
    throw new Error(`Billing status failed (${res.status})`)
  }
  return res.json()
}

// POST endpoints require a Content-Length header (server middleware), so we send
// an empty JSON body. Both return a Stripe-hosted URL the caller redirects to.
// Phase 8.4 — scope='org' routes Checkout / Portal at the OrganizationSubscription
// table (admin-only on the server side; viewers get 403).
export async function startCheckout(
  token: string,
  scope: 'user' | 'org' = 'user',
): Promise<string> {
  const url = scope === 'org'
    ? `${API_BASE}/billing/checkout-session?scope=org`
    : `${API_BASE}/billing/checkout-session`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: '{}',
  })
  if (!res.ok) {
    throw new Error(await errorDetail(res))
  }
  const data = (await res.json()) as { url: string }
  return data.url
}

export async function openBillingPortal(
  token: string,
  scope: 'user' | 'org' = 'user',
): Promise<string> {
  const url = scope === 'org'
    ? `${API_BASE}/billing/portal?scope=org`
    : `${API_BASE}/billing/portal`
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: '{}',
  })
  if (!res.ok) {
    throw new Error(await errorDetail(res))
  }
  const data = (await res.json()) as { url: string }
  return data.url
}
