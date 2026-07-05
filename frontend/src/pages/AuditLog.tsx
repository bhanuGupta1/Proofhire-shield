import { useEffect, useState } from 'react'
import { useAuth, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { getAudit } from '../lib/api'
import type { AuditEntry } from '../lib/types'

const ACTION_LABEL: Record<string, string> = {
  'candidate.created': 'Candidate added',
  'share.created': 'Shortlist shared',
}

function AuditInner() {
  const { getToken } = useAuth()
  const [entries, setEntries] = useState<AuditEntry[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const token = await getToken()
        if (!token) {
          setError('Sign in to view the audit log.')
          return
        }
        setEntries((await getAudit(token)).entries)
      } catch (e) {
        setError((e as Error).message || 'Could not load the audit log.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [getToken])

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-gray-900">Audit Log</h2>
        <p className="text-sm text-gray-500">
          A tamper-evident trail of consequential actions — the platform-level
          counterpart to each scan's Trust Report.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-10 text-center text-sm text-gray-400">Loading…</div>
      ) : entries.length === 0 ? (
        <p className="py-10 text-center text-sm text-gray-400">No activity yet.</p>
      ) : (
        <ol className="relative space-y-3 border-l border-gray-200 pl-5">
          {entries.map((e) => (
            <li key={e.id} className="relative">
              <span className="absolute -left-[23px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-blue-500" />
              <div className="rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
                <div className="flex items-center justify-between gap-2">
                  <span className="rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-semibold text-gray-600">
                    {ACTION_LABEL[e.action] ?? e.action}
                  </span>
                  <span className="text-[11px] text-gray-400">
                    {new Date(e.created_at).toLocaleString()}
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-gray-700">{e.summary}</p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

export function AuditLog() {
  return (
    <>
      <SignedIn>
        <AuditInner />
      </SignedIn>
      <SignedOut>
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">Sign in to view the audit log</p>
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
