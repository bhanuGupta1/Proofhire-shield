import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import {
  addToShortlist,
  getShortlist,
  listCandidates,
  removeFromShortlist,
} from '../lib/api'
import type { Candidate, CandidateCard } from '../lib/types'

export function ShortlistPanel({ jobId }: { jobId: string }) {
  const { getToken } = useAuth()
  const [entries, setEntries] = useState<CandidateCard[]>([])
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [pick, setPick] = useState('')
  const [busy, setBusy] = useState(false)

  async function refresh() {
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to view the shortlist.')
        return
      }
      const [list, cs] = await Promise.all([
        getShortlist(jobId, token),
        listCandidates(token),
      ])
      setEntries(list)
      setCandidates(cs.candidates)
    } catch (e) {
      setError((e as Error).message || 'Could not load shortlist.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  const shortlistedIds = new Set(entries.map((e) => e.id))
  const available = candidates.filter((c) => !shortlistedIds.has(c.id))

  async function withToken(fn: (token: string) => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      await fn(token)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Shortlist
        </h3>
        {available.length > 0 && (
          <div className="flex items-center gap-2">
            <select
              value={pick}
              onChange={(e) => setPick(e.target.value)}
              className="rounded-lg border border-gray-300 bg-white px-2 py-1 text-xs shadow-sm focus:border-blue-400 focus:outline-none"
            >
              <option value="">Add…</option>
              {available.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.full_name}
                </option>
              ))}
            </select>
            <button
              disabled={!pick || busy}
              onClick={() =>
                void withToken((token) => addToShortlist(jobId, pick, token)).then(() =>
                  setPick(''),
                )
              }
              className="rounded-lg bg-gray-900 px-2.5 py-1 text-xs font-semibold text-white shadow-sm transition hover:bg-gray-700 disabled:opacity-50"
            >
              Add
            </button>
          </div>
        )}
      </div>

      {error && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <p className="py-4 text-center text-xs text-gray-400">Loading…</p>
      ) : entries.length === 0 ? (
        <p className="py-4 text-center text-xs text-gray-400">
          No one shortlisted yet.
        </p>
      ) : (
        <ul className="divide-y divide-gray-50">
          {entries.map((c) => (
            <li key={c.id} className="flex items-center justify-between py-2">
              <div className="min-w-0">
                <Link
                  to={`/candidates/${c.id}`}
                  className="text-sm font-medium text-blue-700 hover:underline"
                >
                  {c.full_name}
                </Link>
                {c.headline && (
                  <p className="truncate text-xs text-gray-400">{c.headline}</p>
                )}
              </div>
              <button
                title="Remove"
                onClick={() =>
                  void withToken((token) => removeFromShortlist(jobId, c.id, token))
                }
                className="shrink-0 rounded-md p-1 text-gray-300 transition hover:bg-red-50 hover:text-red-500"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
