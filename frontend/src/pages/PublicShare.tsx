import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { getPublicShare } from '../lib/api'
import type { PublicShare as Share } from '../lib/types'

function riskClasses(level: string | null): string {
  if (level === 'GREEN') return 'bg-green-100 text-green-700'
  if (level === 'ORANGE') return 'bg-amber-100 text-amber-700'
  if (level === 'RED') return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-400'
}

// Standalone, unauthenticated view — rendered OUTSIDE the app shell. This is
// what a client sees when a recruiter sends them a share link.
export function PublicShare() {
  const { token } = useParams<{ token: string }>()
  const [share, setShare] = useState<Share | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      if (!token) return
      try {
        setShare(await getPublicShare(token))
      } catch (e) {
        setError((e as Error).message || 'This link is not available.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [token])

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-3xl items-center gap-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 text-white">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z" /></svg>
          </div>
          <span className="text-sm font-bold text-gray-900">ProofHire Shield</span>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-6 py-10">
        {loading ? (
          <p className="py-16 text-center text-sm text-gray-400">Loading…</p>
        ) : error || !share ? (
          <div className="rounded-xl border border-gray-200 bg-white p-8 text-center shadow-sm">
            <p className="text-sm font-medium text-gray-700">
              {error ?? 'This share link is not available.'}
            </p>
            <p className="mt-1 text-xs text-gray-400">
              The link may have expired or been revoked.
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-gray-900">
                Candidate Shortlist
              </h1>
              <p className="text-sm text-gray-500">
                {share.job_title}
                {share.client_name ? ` · ${share.client_name}` : ''}
              </p>
            </div>

            {share.candidates.length === 0 ? (
              <p className="rounded-xl border border-gray-200 bg-white p-8 text-center text-sm text-gray-400 shadow-sm">
                No candidates have been shortlisted yet.
              </p>
            ) : (
              <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
                <table className="w-full text-left text-sm">
                  <thead className="border-b border-gray-100 bg-gray-50/60 text-xs uppercase tracking-wide text-gray-400">
                    <tr>
                      <th className="px-4 py-3 font-semibold">Candidate</th>
                      <th className="px-4 py-3 font-semibold">Headline</th>
                      <th className="px-4 py-3 font-semibold">CV Risk</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {share.candidates.map((c, i) => (
                      <tr key={i}>
                        <td className="px-4 py-3 font-medium text-gray-900">{c.full_name}</td>
                        <td className="px-4 py-3 text-gray-500">{c.headline ?? '—'}</td>
                        <td className="px-4 py-3">
                          {c.risk_level ? (
                            <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wide ${riskClasses(c.risk_level)}`}>
                              {c.risk_level}
                            </span>
                          ) : (
                            <span className="text-xs text-gray-300">—</span>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}

            <p className="text-xs text-gray-400">
              Each candidate's CV was scanned by ProofHire Shield for hidden
              instructions and personal data before inclusion. This is a screening
              aid and does not constitute a final hiring decision.
            </p>
          </div>
        )}
      </main>
    </div>
  )
}
