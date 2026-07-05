import { useState } from 'react'
import { useAuth, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import { talentSearch } from '../lib/api'
import type { TalentHit } from '../lib/types'

function riskClasses(level: string | null): string {
  if (level === 'GREEN') return 'bg-green-100 text-green-700'
  if (level === 'ORANGE') return 'bg-amber-100 text-amber-700'
  if (level === 'RED') return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-400'
}

function TalentInner() {
  const { getToken } = useAuth()
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<TalentHit[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function search(e: React.FormEvent) {
    e.preventDefault()
    if (!query.trim()) return
    setLoading(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to search your talent pool.')
        return
      }
      const res = await talentSearch(query.trim(), token)
      setResults(res.results)
    } catch (e) {
      setError((e as Error).message || 'Search failed.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-gray-900">Talent Search</h2>
        <p className="text-sm text-gray-500">
          Search your saved candidates by skill, role, or keyword.
        </p>
      </div>

      <form onSubmit={search} className="flex items-center gap-2">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="e.g. python django aws"
          className="grow rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <button
          type="submit"
          disabled={!query.trim() || loading}
          className="rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:opacity-90 disabled:opacity-50"
        >
          {loading ? 'Searching…' : 'Search'}
        </button>
      </form>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {results !== null &&
        (results.length === 0 ? (
          <p className="py-10 text-center text-sm text-gray-400">
            No candidates matched “{query}”.
          </p>
        ) : (
          <ul className="space-y-2">
            {results.map((h) => (
              <li
                key={h.candidate_id}
                className="flex items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm"
              >
                <div className="min-w-0">
                  <Link
                    to={`/candidates/${h.candidate_id}`}
                    className="text-sm font-semibold text-blue-700 hover:underline"
                  >
                    {h.full_name}
                  </Link>
                  {h.headline && <p className="truncate text-xs text-gray-400">{h.headline}</p>}
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  {h.risk_level && (
                    <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wide ${riskClasses(h.risk_level)}`}>
                      {h.risk_level}
                    </span>
                  )}
                  <span className="text-sm font-bold text-gray-700">{h.score}%</span>
                </div>
              </li>
            ))}
          </ul>
        ))}
    </div>
  )
}

export function TalentSearch() {
  return (
    <>
      <SignedIn>
        <TalentInner />
      </SignedIn>
      <SignedOut>
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">Sign in to search talent</p>
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
