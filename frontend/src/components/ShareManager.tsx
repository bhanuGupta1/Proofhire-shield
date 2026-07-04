import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { createShare, listShares, revokeShare } from '../lib/api'
import type { ClientShare } from '../lib/types'

function shareUrl(path: string): string {
  if (typeof window === 'undefined') return path
  return `${window.location.origin}${path}`
}

export function ShareManager({ jobId }: { jobId: string }) {
  const { getToken } = useAuth()
  const [shares, setShares] = useState<ClientShare[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [expiry, setExpiry] = useState('') // '' = never
  const [copied, setCopied] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  async function refresh() {
    try {
      const token = await getToken()
      if (!token) return
      setShares(await listShares(jobId, token))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  async function create() {
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      const days = expiry ? Number(expiry) : undefined
      await createShare(jobId, token, { expires_in_days: days })
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function revoke(id: string) {
    const token = await getToken()
    if (!token) return
    await revokeShare(id, token)
    await refresh()
  }

  function copy(path: string) {
    const url = shareUrl(path)
    void navigator.clipboard?.writeText(url)
    setCopied(path)
    window.setTimeout(() => setCopied(null), 1500)
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Client share links
        </h3>
        <div className="flex items-center gap-2">
          <select
            value={expiry}
            onChange={(e) => setExpiry(e.target.value)}
            className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-blue-400 focus:outline-none"
          >
            <option value="">Never expires</option>
            <option value="7">Expires in 7 days</option>
            <option value="30">Expires in 30 days</option>
          </select>
          <button
            onClick={() => void create()}
            disabled={busy}
            className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-gray-700 disabled:opacity-50"
          >
            Create link
          </button>
        </div>
      </div>

      <p className="mb-3 text-xs text-gray-400">
        Anyone with a link sees this job's shortlist read-only — no login, no
        candidate contact details.
      </p>

      {error && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <p className="py-3 text-center text-xs text-gray-400">Loading…</p>
      ) : shares.length === 0 ? (
        <p className="py-3 text-center text-xs text-gray-400">No active links.</p>
      ) : (
        <ul className="space-y-2">
          {shares.map((s) => (
            <li
              key={s.id}
              className="flex items-center justify-between gap-2 rounded-lg border border-gray-100 bg-gray-50/60 px-3 py-2"
            >
              <div className="min-w-0">
                <p className="truncate font-mono text-[11px] text-gray-600">
                  {shareUrl(s.path)}
                </p>
                <p className="text-[10px] text-gray-400">
                  {s.expires_at
                    ? `Expires ${new Date(s.expires_at).toLocaleDateString()}`
                    : 'Never expires'}
                </p>
              </div>
              <div className="flex shrink-0 items-center gap-1.5">
                <button
                  onClick={() => copy(s.path)}
                  className="rounded-md border border-gray-300 bg-white px-2 py-1 text-[11px] font-semibold text-gray-600 transition hover:bg-gray-100"
                >
                  {copied === s.path ? 'Copied!' : 'Copy'}
                </button>
                <button
                  onClick={() => void revoke(s.id)}
                  title="Revoke"
                  className="rounded-md p-1 text-gray-300 transition hover:bg-red-50 hover:text-red-500"
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
