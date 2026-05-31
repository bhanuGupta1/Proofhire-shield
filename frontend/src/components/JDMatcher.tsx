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
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <h3 className="mb-1 text-sm font-semibold text-gray-800">Job description match</h3>
      <p className="mb-3 text-xs text-gray-400">
        Paste a job description to see how this candidate&rsquo;s skills line up. Keyword-based — verify with the candidate.
      </p>
      <textarea
        value={jd}
        onChange={(e) => setJd(e.target.value)}
        placeholder="Paste the job description here…"
        maxLength={20000}
        rows={6}
        className="w-full resize-y rounded-lg border border-gray-300 p-3 text-sm text-gray-800 focus:border-blue-500 focus:outline-none"
      />
      <button
        onClick={handleMatch}
        disabled={loading || !jd.trim()}
        className="mt-3 rounded-lg bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
      >
        {loading ? 'Matching…' : 'Match against JD'}
      </button>

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

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
