import { useEffect, useState } from 'react'
import { useAuth, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import { listCandidates } from '../lib/api'
import type { Candidate } from '../lib/types'

const STATUS_OPTIONS = ['', 'new', 'reviewing', 'shortlisted', 'rejected', 'hired']

function RiskBadge({ level }: { level: Candidate['risk_level'] }) {
  if (!level) return <span className="text-xs text-gray-300">—</span>
  const cls =
    level === 'GREEN'
      ? 'bg-green-100 text-green-700'
      : level === 'ORANGE'
        ? 'bg-amber-100 text-amber-700'
        : 'bg-red-100 text-red-700'
  return (
    <span className={`rounded-full px-2 py-0.5 text-[11px] font-bold tracking-wide ${cls}`}>
      {level}
    </span>
  )
}

function CandidatesInner() {
  const { getToken } = useAuth()
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('')

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to view candidates.')
        return
      }
      const res = await listCandidates(token, {
        q: q || undefined,
        status: status || undefined,
      })
      setCandidates(res.candidates)
    } catch (e) {
      setError((e as Error).message || 'Could not load candidates.')
    } finally {
      setLoading(false)
    }
  }

  // Reload when the status filter changes; search is applied on submit.
  useEffect(() => {
    void load()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-gray-900">Candidates</h2>
          <p className="text-sm text-gray-500">
            People you've saved from a scan or added manually.
          </p>
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            void load()
          }}
          className="flex grow items-center gap-2"
        >
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name…"
            className="grow rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
          <button
            type="submit"
            className="rounded-lg bg-gray-900 px-3 py-2 text-sm font-medium text-white shadow-sm transition hover:bg-gray-700"
          >
            Search
          </button>
        </form>
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none"
        >
          {STATUS_OPTIONS.map((s) => (
            <option key={s} value={s}>
              {s === '' ? 'All statuses' : s}
            </option>
          ))}
        </select>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-16 text-center text-sm text-gray-400">Loading…</div>
      ) : candidates.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">No candidates yet</p>
          <p className="mt-1 text-xs text-gray-400">
            Run a scan and hit “Save as candidate”, or add one from a CV.
          </p>
          <Link
            to="/"
            className="mt-4 inline-block rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm"
          >
            New scan
          </Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-100 bg-gray-50/60 text-xs uppercase tracking-wide text-gray-400">
              <tr>
                <th className="px-4 py-3 font-semibold">Name</th>
                <th className="px-4 py-3 font-semibold">Headline</th>
                <th className="px-4 py-3 font-semibold">Status</th>
                <th className="px-4 py-3 font-semibold">Risk</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {candidates.map((c) => (
                <tr key={c.id} className="transition hover:bg-blue-50/40">
                  <td className="px-4 py-3">
                    <Link
                      to={`/candidates/${c.id}`}
                      className="font-medium text-blue-700 hover:underline"
                    >
                      {c.full_name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{c.headline ?? '—'}</td>
                  <td className="px-4 py-3">
                    <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs font-medium capitalize text-gray-600">
                      {c.status}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    <RiskBadge level={c.risk_level} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

export function CandidatesList() {
  return (
    <>
      <SignedIn>
        <CandidatesInner />
      </SignedIn>
      <SignedOut>
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">Sign in to manage candidates</p>
          <SignInButton mode="modal">
            <button className="mt-4 rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white shadow-sm">
              Sign in
            </button>
          </SignInButton>
        </div>
      </SignedOut>
    </>
  )
}
