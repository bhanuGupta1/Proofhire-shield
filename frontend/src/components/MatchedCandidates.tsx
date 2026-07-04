import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import { addPlacement, addToShortlist, autoMatch } from '../lib/api'
import type { MatchCandidate } from '../lib/types'

function ScoreRing({ score }: { score: number }) {
  const color =
    score >= 75 ? 'text-green-600' : score >= 40 ? 'text-amber-600' : 'text-gray-400'
  return <span className={`text-sm font-bold ${color}`}>{score}%</span>
}

export function MatchedCandidates({ jobId }: { jobId: string }) {
  const { getToken } = useAuth()
  const [matches, setMatches] = useState<MatchCandidate[]>([])
  const [required, setRequired] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [note, setNote] = useState<Record<string, string>>({})

  useEffect(() => {
    async function load() {
      try {
        const token = await getToken()
        if (!token) {
          setError('Sign in to see matches.')
          return
        }
        const res = await autoMatch(jobId, token)
        setMatches(res.matches)
        setRequired(res.required_skills)
      } catch (e) {
        setError((e as Error).message || 'Could not compute matches.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [jobId, getToken])

  async function act(
    candidateId: string,
    fn: (token: string) => Promise<unknown>,
    okLabel: string,
  ) {
    try {
      const token = await getToken()
      if (!token) return
      await fn(token)
      setNote((n) => ({ ...n, [candidateId]: okLabel }))
    } catch (e) {
      setNote((n) => ({ ...n, [candidateId]: (e as Error).message }))
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Matched candidates
      </h3>

      {loading ? (
        <p className="py-4 text-center text-xs text-gray-400">Scoring…</p>
      ) : error ? (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      ) : required.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-400">
          Add <span className="font-medium">required skills</span> to this job to rank
          candidates by fit.
        </p>
      ) : matches.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-400">
          No candidates match these skills yet.
        </p>
      ) : (
        <ul className="space-y-2.5">
          {matches.map((m) => (
            <li key={m.candidate_id} className="rounded-lg border border-gray-100 bg-gray-50/60 p-3">
              <div className="flex items-center justify-between gap-2">
                <Link
                  to={`/candidates/${m.candidate_id}`}
                  className="text-sm font-semibold text-blue-700 hover:underline"
                >
                  {m.full_name}
                </Link>
                <ScoreRing score={m.score} />
              </div>
              {m.headline && <p className="text-xs text-gray-400">{m.headline}</p>}
              <div className="mt-1.5 flex flex-wrap gap-1">
                {m.matched_skills.map((s) => (
                  <span key={s} className="rounded-full bg-green-50 px-2 py-0.5 text-[10px] font-medium text-green-700">
                    {s}
                  </span>
                ))}
                {m.missing_skills.map((s) => (
                  <span key={s} className="rounded-full bg-gray-100 px-2 py-0.5 text-[10px] font-medium text-gray-400 line-through">
                    {s}
                  </span>
                ))}
              </div>
              <div className="mt-2 flex items-center gap-2">
                <button
                  onClick={() =>
                    void act(
                      m.candidate_id,
                      (t) => addPlacement(jobId, m.candidate_id, t),
                      'Added to pipeline',
                    )
                  }
                  className="rounded-md border border-gray-300 bg-white px-2 py-1 text-[11px] font-semibold text-gray-600 transition hover:bg-gray-100"
                >
                  + Pipeline
                </button>
                <button
                  onClick={() =>
                    void act(
                      m.candidate_id,
                      (t) => addToShortlist(jobId, m.candidate_id, t),
                      'Shortlisted',
                    )
                  }
                  className="rounded-md border border-gray-300 bg-white px-2 py-1 text-[11px] font-semibold text-gray-600 transition hover:bg-gray-100"
                >
                  ★ Shortlist
                </button>
                {note[m.candidate_id] && (
                  <span className="text-[11px] text-gray-400">{note[m.candidate_id]}</span>
                )}
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
