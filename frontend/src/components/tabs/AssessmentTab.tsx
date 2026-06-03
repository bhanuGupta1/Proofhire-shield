import { useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import type { ScanResult, AssessmentReport, BillingStatus } from '../../lib/types'
import { generateAssessment, sendFollowup } from '../../lib/api'

interface Props {
  result: ScanResult
  billing: BillingStatus | null
  onUpgrade: () => void
}

const FOLLOWUP_MAX = 500


function CoPilotCard({
  scanId,
  isPro,
  onUpgrade,
}: {
  scanId: string | null
  isPro: boolean
  onUpgrade: () => void
}) {
  const { getToken } = useAuth()
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // The endpoint identifies the candidate by scan_id, so a re-uploaded
  // (history-loaded) ScanResult without a scan_id can't be queried.
  // Surface that as a friendly explanation instead of a 422 / 404 dead-end.
  const canAsk = isPro && Boolean(scanId)

  async function handleAsk() {
    if (!canAsk || !question.trim() || !scanId) return
    setBusy(true)
    setError(null)
    setAnswer(null)
    try {
      const token = await getToken()
      if (!token) {
        setError('Please sign in.')
        return
      }
      const r = await sendFollowup(scanId, question.trim(), token)
      setAnswer(r.answer)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  if (!isPro) {
    return (
      <div className="rounded-xl border border-purple-200 bg-gradient-to-br from-purple-50 to-indigo-50 p-5">
        <div className="flex items-start gap-3">
          <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 shadow-sm">
            <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8 12h8m-4-4v8m9-4a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
          </div>
          <div className="grow">
            <h3 className="text-sm font-semibold text-purple-900">Ask a follow-up</h3>
            <p className="mt-1 text-xs text-purple-800">
              Pro users can ask a follow-up question about this candidate — strengths to probe in the interview, evidence gaps to clarify, fit for a specific role.
            </p>
            <button
              onClick={onUpgrade}
              className="mt-3 inline-flex items-center gap-1.5 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:from-purple-700 hover:to-indigo-700 hover:shadow-md"
            >
              Upgrade to Pro to ask follow-up questions
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6"/></svg>
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-purple-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-start gap-3">
        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-purple-500 to-indigo-600 shadow-sm">
          <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M8 12h8m-4-4v8m9-4a9 9 0 11-18 0 9 9 0 0118 0z"/>
          </svg>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-900">Ask the co-pilot</h3>
          <p className="text-xs text-gray-500">
            One question about this candidate, grounded in their scan signals + CV. Plain-prose answer.
          </p>
        </div>
      </div>

      {!scanId && (
        <p className="mb-2 text-xs italic text-amber-700">
          Re-upload the CV to ask a follow-up — this view was loaded from history.
        </p>
      )}

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value.slice(0, FOLLOWUP_MAX))}
        placeholder="e.g. How strong is the candidate's AWS experience based on the evidence?"
        rows={3}
        maxLength={FOLLOWUP_MAX}
        disabled={!canAsk || busy}
        className="w-full resize-y rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-800 shadow-inner transition focus:border-purple-500 focus:ring-2 focus:ring-purple-100 focus:outline-none disabled:cursor-not-allowed disabled:bg-gray-50"
      />
      <div className="mt-2 flex items-center justify-between">
        <span className="text-xs text-gray-400">
          {question.length} / {FOLLOWUP_MAX}
        </span>
        <button
          onClick={handleAsk}
          disabled={!canAsk || !question.trim() || busy}
          className="inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-purple-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:from-purple-700 hover:to-indigo-700 hover:shadow-md disabled:cursor-not-allowed disabled:from-gray-400 disabled:to-gray-500 disabled:shadow-none"
        >
          {busy ? (
            <>
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              Asking…
            </>
          ) : (
            <>
              Ask
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6"/></svg>
            </>
          )}
        </button>
      </div>

      {answer && (
        <div className="mt-4 rounded-lg border border-gray-200 bg-gray-50/80 p-4 shadow-inner">
          <p className="mb-1 text-xs font-semibold uppercase tracking-wider text-gray-400">
            Co-pilot
          </p>
          <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-800">
            {answer}
          </p>
        </div>
      )}
      {error && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          {error}
        </div>
      )}
    </div>
  )
}

function scoreColour(score: number): string {
  if (score >= 70) return 'text-green-600 border-green-500'
  if (score >= 40) return 'text-amber-600 border-amber-500'
  return 'text-red-600 border-red-500'
}

export function AssessmentTab({ result, billing, onUpgrade }: Props) {
  const { getToken, isSignedIn } = useAuth()
  const [roleContext, setRoleContext] = useState('')
  const [report, setReport] = useState<AssessmentReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGenerate() {
    setLoading(true)
    setError(null)
    try {
      const token = isSignedIn ? await getToken() : null
      const r = await generateAssessment(result, roleContext.trim() || undefined, token)
      setReport(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  // Phase 9 — Assessment is now open to any signed-in caller (Free or Pro).
  // The Pro differentiator moved to the follow-up co-pilot card rendered
  // below the report. Anonymous still gets the sign-in CTA so we never
  // surface "Generate" against an endpoint that will 401.
  if (!isSignedIn) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-6 text-center">
        <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-blue-50 text-2xl">
          🔒
        </div>
        <h3 className="mb-1 text-sm font-semibold text-gray-800">Sign in to generate assessments</h3>
        <p className="mx-auto mb-4 max-w-sm text-xs text-gray-500">
          Create a free account to get AI-powered candidate assessments with strengths,
          concerns, interview focus, and a hiring recommendation.
        </p>
        <a
          href="/sign-in"
          className="inline-block rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700"
        >
          Sign in — it&apos;s free
        </a>
      </div>
    )
  }

  if (!report) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <h3 className="mb-2 text-sm font-semibold text-gray-800">AI assessment report</h3>
        <p className="mb-4 text-xs text-gray-500">
          Generate a structured candidate assessment under the ProofHire v1 framework. The
          report covers profile, strengths, concerns, interview focus, verifiability, trust
          posture, and a recommendation. Server-side Claude API key required.
        </p>
        <label className="block">
          <span className="text-xs font-medium text-gray-600">Role context (optional)</span>
          <textarea
            value={roleContext}
            onChange={(e) => setRoleContext(e.target.value)}
            placeholder="e.g. Senior backend engineer at a fintech, 5+ yrs, AWS-native"
            maxLength={2000}
            rows={3}
            className="mt-1 w-full resize-y rounded-lg border border-gray-300 p-3 text-sm text-gray-800 focus:border-blue-500 focus:outline-none"
          />
        </label>
        <button
          onClick={handleGenerate}
          disabled={loading}
          className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {loading ? 'Generating…' : 'Generate assessment'}
        </button>
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </div>
    )
  }

  return (
    <div className="space-y-5">
      {/* Headline */}
      <div className="rounded-xl border border-gray-200 bg-white p-5">
        <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
          Assessment headline
        </p>
        <p className="mt-1 text-lg font-semibold text-gray-900">{report.headline}</p>
      </div>

      {/* Score + recommendation */}
      <div className="flex items-center gap-4 rounded-xl border border-gray-200 bg-white p-5">
        <div
          className={`flex h-20 w-20 shrink-0 flex-col items-center justify-center rounded-full border-8 ${scoreColour(
            report.overall_score,
          )}`}
        >
          <span className="text-2xl font-bold leading-none">{report.overall_score}</span>
          <span className="text-xs text-gray-400">/ 100</span>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wide text-gray-500">
            Recommendation
          </p>
          <p className="text-sm font-semibold text-gray-800">{report.overall_recommendation}</p>
        </div>
      </div>

      {/* Dimensions */}
      <div className="space-y-3">
        {report.dimensions.map((d, i) => (
          <div key={i} className="rounded-xl border border-gray-200 bg-white p-5">
            <h3 className="mb-2 text-sm font-semibold uppercase tracking-wide text-gray-600">
              {d.name}
            </h3>
            <p className="whitespace-pre-wrap text-sm text-gray-700">{d.text}</p>
            {d.bullets.length > 0 && (
              <ul className="mt-3 space-y-1">
                {d.bullets.map((b, j) => (
                  <li key={j} className="flex gap-2 text-sm text-gray-700">
                    <span className="text-blue-500">&rsaquo;</span>
                    <span>{b}</span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>

      {/* Next steps */}
      <div className="rounded-xl border border-blue-200 bg-blue-50 p-5">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-blue-700">
          Next steps (24h)
        </h3>
        <ol className="space-y-2">
          {report.next_steps.map((s, i) => (
            <li key={i} className="flex gap-3 text-sm text-blue-900">
              <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-blue-600 text-xs font-bold text-white">
                {i + 1}
              </span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
      </div>

      {/* Phase 9 — recruiter co-pilot card. Shown to every signed-in caller;
          the card itself decides whether to render the input (Pro) or the
          upgrade CTA (Free). */}
      <CoPilotCard
        scanId={result.scan_id ?? null}
        isPro={billing?.is_pro ?? false}
        onUpgrade={onUpgrade}
      />

      {/* Framework label + regenerate */}
      <div className="flex items-center justify-between">
        <p className="text-xs italic text-gray-400">
          Framework: {report.framework}. Heuristic + LLM-assisted — verify all claims with the candidate.
        </p>
        <button
          onClick={() => {
            setReport(null)
            setError(null)
          }}
          className="text-xs text-blue-600 hover:underline"
        >
          &lsaquo; Generate a different assessment
        </button>
      </div>
    </div>
  )
}
