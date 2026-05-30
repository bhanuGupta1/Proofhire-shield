import { useState } from 'react'
import type { ScanResult, AssessmentReport } from '../../lib/types'
import { generateAssessment } from '../../lib/api'

interface Props {
  result: ScanResult
}

function scoreColour(score: number): string {
  if (score >= 70) return 'text-green-600 border-green-500'
  if (score >= 40) return 'text-amber-600 border-amber-500'
  return 'text-red-600 border-red-500'
}

export function AssessmentTab({ result }: Props) {
  const [roleContext, setRoleContext] = useState('')
  const [report, setReport] = useState<AssessmentReport | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleGenerate() {
    setLoading(true)
    setError(null)
    try {
      const r = await generateAssessment(result, roleContext.trim() || undefined)
      setReport(r)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
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
