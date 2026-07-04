import type {
  AssessmentReport,
  AuditList,
  AutoMatchResponse,
  BillingStatus,
  BoardCard,
  Candidate,
  CandidateCard,
  CandidateCreate,
  CandidateListResponse,
  CandidateUpdate,
  Client,
  ClientCreate,
  ClientListResponse,
  ClientShare,
  DashboardMetrics,
  FollowupResponse,
  JDMatchResult,
  Job,
  JobCreate,
  JobListResponse,
  JobUpdate,
  NotificationList,
  OutreachDraft,
  OutreachMessage,
  PipelineBoard,
  PipelineStageView,
  PublicShare,
  ScanListResponse,
  ScanResponse,
  ScanResult,
  TalentSearchResponse,
  TodayQueue,
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

export async function scanCV(
  file: File,
  token?: string | null,
  engine?: 'regex' | 'llm',
): Promise<ScanResponse> {
  const form = new FormData()
  form.append('file', file)
  // Do not set Content-Type here — fetch + FormData generates the multipart
  // boundary header automatically; overriding it breaks the parse.
  // Phase 9 v4 — match_engine is a query param so the existing multipart
  // body shape stays untouched.
  const url = engine
    ? `${API_BASE}/scan-cv?match_engine=${engine}`
    : `${API_BASE}/scan-cv`
  const res = await fetch(url, {
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

// Phase 9 — recruiter co-pilot follow-up. Auth + Pro required server-side;
// the UI shows an upgrade CTA before ever calling this so most non-Pro users
// never hit a 402.
export async function sendFollowup(
  scanId: string,
  question: string,
  token: string,
): Promise<FollowupResponse> {
  const res = await fetch(`${API_BASE}/assessment/followup`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify({ scan_id: scanId, question }),
  })
  if (!res.ok) {
    throw new Error(await errorDetail(res))
  }
  return res.json()
}

// ── Platform: candidates ─────────────────────────────────────────────────────

export async function createCandidate(
  body: CandidateCreate,
  token: string,
): Promise<Candidate> {
  const res = await fetch(`${API_BASE}/candidates`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function listCandidates(
  token: string,
  params?: { status?: string; q?: string },
): Promise<CandidateListResponse> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  if (params?.q) qs.set('q', params.q)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${API_BASE}/candidates${suffix}`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function getCandidate(
  id: string,
  token: string,
): Promise<Candidate> {
  const res = await fetch(`${API_BASE}/candidates/${id}`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function updateCandidate(
  id: string,
  body: CandidateUpdate,
  token: string,
): Promise<Candidate> {
  const res = await fetch(`${API_BASE}/candidates/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function deleteCandidate(id: string, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/candidates/${id}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

// ── Platform: jobs ───────────────────────────────────────────────────────────

export async function createJob(body: JobCreate, token: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function listJobs(
  token: string,
  params?: { status?: string },
): Promise<JobListResponse> {
  const qs = new URLSearchParams()
  if (params?.status) qs.set('status', params.status)
  const suffix = qs.toString() ? `?${qs.toString()}` : ''
  const res = await fetch(`${API_BASE}/jobs${suffix}`, { headers: bearer(token) })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function getJob(id: string, token: string): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, { headers: bearer(token) })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function updateJob(
  id: string,
  body: JobUpdate,
  token: string,
): Promise<Job> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function deleteJob(id: string, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/jobs/${id}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

// ── Platform: pipeline ───────────────────────────────────────────────────────

export async function getPipeline(
  jobId: string,
  token: string,
): Promise<PipelineBoard> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/pipeline`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function addStage(
  jobId: string,
  name: string,
  token: string,
): Promise<PipelineStageView> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/stages`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify({ name }),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function deleteStage(stageId: string, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/pipeline/stages/${stageId}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

export async function addPlacement(
  jobId: string,
  candidateId: string,
  token: string,
  stageId?: string,
): Promise<BoardCard> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/placements`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify({ candidate_id: candidateId, stage_id: stageId }),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function movePlacement(
  placementId: string,
  stageId: string,
  token: string,
): Promise<BoardCard> {
  const res = await fetch(`${API_BASE}/pipeline/placements/${placementId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify({ stage_id: stageId }),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function removePlacement(
  placementId: string,
  token: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/pipeline/placements/${placementId}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

// ── Platform: shortlist ──────────────────────────────────────────────────────

export async function getShortlist(
  jobId: string,
  token: string,
): Promise<CandidateCard[]> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/shortlist`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function addToShortlist(
  jobId: string,
  candidateId: string,
  token: string,
): Promise<CandidateCard> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/shortlist`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify({ candidate_id: candidateId }),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function removeFromShortlist(
  jobId: string,
  candidateId: string,
  token: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/shortlist/${candidateId}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

// ── Platform: matching & talent search ───────────────────────────────────────

export async function autoMatch(
  jobId: string,
  token: string,
): Promise<AutoMatchResponse> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/auto-match`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: '{}',
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function talentSearch(
  query: string,
  token: string,
): Promise<TalentSearchResponse> {
  const res = await fetch(`${API_BASE}/talent/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify({ query }),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

// ── Platform: dashboard & today ──────────────────────────────────────────────

export async function getDashboardMetrics(
  token: string,
): Promise<DashboardMetrics> {
  const res = await fetch(`${API_BASE}/dashboard/metrics`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function getToday(token: string): Promise<TodayQueue> {
  const res = await fetch(`${API_BASE}/today`, { headers: bearer(token) })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

// ── Platform: clients ────────────────────────────────────────────────────────

export async function createClient(
  body: ClientCreate,
  token: string,
): Promise<Client> {
  const res = await fetch(`${API_BASE}/clients`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function listClients(token: string): Promise<ClientListResponse> {
  const res = await fetch(`${API_BASE}/clients`, { headers: bearer(token) })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function deleteClient(id: string, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/clients/${id}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

// ── Platform: shares ─────────────────────────────────────────────────────────

export async function createShare(
  jobId: string,
  token: string,
  opts?: { label?: string; expires_in_days?: number },
): Promise<ClientShare> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(opts ?? {}),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function listShares(
  jobId: string,
  token: string,
): Promise<ClientShare[]> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/shares`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return (await res.json()).shares
}

export async function revokeShare(shareId: string, token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/shares/${shareId}`, {
    method: 'DELETE',
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

// Public share view — no auth header; the token in the path is the credential.
export async function getPublicShare(token: string): Promise<PublicShare> {
  const res = await fetch(`${API_BASE}/share/${token}`)
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

// ── Platform: notifications & outreach ───────────────────────────────────────

export async function listNotifications(
  token: string,
): Promise<NotificationList> {
  const res = await fetch(`${API_BASE}/notifications`, { headers: bearer(token) })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function getUnreadCount(token: string): Promise<number> {
  const res = await fetch(`${API_BASE}/notifications/unread-count`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return (await res.json()).count
}

export async function markNotificationRead(
  id: string,
  token: string,
): Promise<void> {
  const res = await fetch(`${API_BASE}/notifications/${id}/read`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: '{}',
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

export async function markAllNotificationsRead(token: string): Promise<void> {
  const res = await fetch(`${API_BASE}/notifications/read-all`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: '{}',
  })
  if (!res.ok) throw new Error(await errorDetail(res))
}

export async function listOutreach(
  candidateId: string,
  token: string,
): Promise<OutreachMessage[]> {
  const res = await fetch(`${API_BASE}/candidates/${candidateId}/outreach`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function logOutreach(
  candidateId: string,
  body: { channel: string; subject?: string; body: string },
  token: string,
): Promise<OutreachMessage> {
  const res = await fetch(`${API_BASE}/candidates/${candidateId}/outreach`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: JSON.stringify(body),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

export async function draftOutreach(
  candidateId: string,
  token: string,
): Promise<OutreachDraft> {
  const res = await fetch(`${API_BASE}/candidates/${candidateId}/outreach/draft`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...bearer(token) },
    body: '{}',
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

// ── Platform: audit ──────────────────────────────────────────────────────────

export async function getAudit(token: string): Promise<AuditList> {
  const res = await fetch(`${API_BASE}/audit`, { headers: bearer(token) })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.json()
}

// The report PDF endpoint needs an auth header, so it can't be a plain <a href>.
// Fetch the bytes and hand back a blob the caller turns into a download.
export async function downloadReportPdf(
  jobId: string,
  token: string,
): Promise<Blob> {
  const res = await fetch(`${API_BASE}/jobs/${jobId}/report.pdf`, {
    headers: bearer(token),
  })
  if (!res.ok) throw new Error(await errorDetail(res))
  return res.blob()
}
