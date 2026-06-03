import { useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { matchJD } from '../lib/api'
import type { JDMatchResult } from '../lib/types'

interface Props {
  cvText: string
}

function scoreColour(score: number): string {
  if (score >= 70) return 'text-green-600 border-green-500'
  if (score >= 40) return 'text-amber-600 border-amber-500'
  return 'text-red-600 border-red-500'
}

function scoreLabel(score: number): string {
  if (score >= 70) return 'Strong match'
  if (score >= 40) return 'Partial match'
  return 'Weak match'
}

function SkillColumn({
  title,
  skills,
  chip,
  empty,
  prefix = '',
}: {
  title: string
  skills: string[]
  chip: string
  empty: string
  prefix?: string
}) {
  return (
    <div>
      <p className="mb-2 text-xs font-medium uppercase tracking-wide text-gray-400">
        {title} ({skills.length})
      </p>
      {skills.length > 0 ? (
        <div className="flex flex-wrap gap-1.5">
          {skills.map((s) => (
            <span key={s} className={`rounded-md border px-2 py-0.5 text-xs font-medium ${chip}`}>
              {prefix}
              {s}
            </span>
          ))}
        </div>
      ) : (
        <p className="text-xs text-gray-300">{empty}</p>
      )}
    </div>
  )
}

export function JDMatcher({ cvText }: Props) {
  const { getToken, isSignedIn } = useAuth()
  const [jd, setJd] = useState('')
  const [result, setResult] = useState<JDMatchResult | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleMatch() {
    if (!jd.trim()) return
    setLoading(true)
    setError(null)
    try {
      const token = isSignedIn ? await getToken() : null
      setResult(await matchJD(cvText, jd, token))
    } catch {
      setError('Could not run the match. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white/80 p-5 shadow-sm backdrop-blur-sm">
      <div className="mb-3 flex items-start gap-2">
        <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-blue-50 to-indigo-100 ring-1 ring-blue-100">
          <svg className="h-3.5 w-3.5 text-blue-600" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4"/></svg>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-gray-800">Job description match</h3>
          <p className="text-xs text-gray-400">
            Paste a job description to see how this candidate&rsquo;s skills line up. Keyword-based — verify with the candidate.
          </p>
        </div>
      </div>
      <textarea
        value={jd}
        onChange={(e) => setJd(e.target.value)}
        placeholder="Paste the job description here…"
        maxLength={20000}
        rows={6}
        className="w-full resize-y rounded-lg border border-gray-300 bg-white p-3 text-sm text-gray-800 shadow-inner transition focus:border-blue-500 focus:ring-2 focus:ring-blue-100 focus:outline-none"
      />
      <button
        onClick={handleMatch}
        disabled={loading || !jd.trim()}
        className="mt-3 inline-flex items-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:from-blue-700 hover:to-indigo-700 hover:shadow-md disabled:cursor-not-allowed disabled:from-gray-400 disabled:to-gray-500 disabled:shadow-none"
      >
        {loading ? (
          <>
            <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
            </svg>
            Matching…
          </>
        ) : (
          <>
            Match against JD
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6"/></svg>
          </>
        )}
      </button>

      {error && (
        <div className="mt-3 inline-flex items-center gap-2 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
          <svg className="h-4 w-4 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          {error}
        </div>
      )}

      {result && (
        <div className="mt-5 space-y-5">
          <div className="flex flex-col items-center">
            <div
              className={`flex h-28 w-28 flex-col items-center justify-center rounded-full border-8 ${scoreColour(result.match_score)}`}
            >
              <span className="text-3xl font-bold leading-none">{result.match_score}</span>
              <span className="text-xs text-gray-400">/ 100</span>
            </div>
            <p className={`mt-2 text-sm font-semibold ${scoreColour(result.match_score).split(' ')[0]}`}>
              {scoreLabel(result.match_score)}
            </p>
          </div>

          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <SkillColumn
              title="Matched skills"
              skills={result.matched_skills}
              chip="bg-green-50 text-green-700 border-green-200"
              empty="No overlapping skills"
            />
            <SkillColumn
              title="Missing skills"
              skills={result.missing_skills}
              chip="bg-red-50 text-red-700 border-red-200"
              prefix="⚠ "
              empty="No gaps — covers the JD"
            />
            <SkillColumn
              title="Bonus skills"
              skills={result.bonus_skills}
              chip="bg-blue-50 text-blue-700 border-blue-200"
              empty="No extras beyond the JD"
            />
          </div>
        </div>
      )}
    </div>
  )
}
