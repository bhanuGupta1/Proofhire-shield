import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { listScans } from '../lib/api'
import type { ScanSummary, RiskLevel } from '../lib/types'

const RISK_PILL: Record<RiskLevel, string> = {
  GREEN: 'bg-green-100 text-green-700',
  ORANGE: 'bg-amber-100 text-amber-700',
  RED: 'bg-red-100 text-red-700',
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso)
    return (
      d.toLocaleDateString(undefined, { year: 'numeric', month: 'short', day: 'numeric' }) +
      ' ' +
      d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' })
    )
  } catch {
    return iso
  }
}

interface Props {
  refreshKey?: number
  onSelect?: (scanId: string) => void
}

export function HistoryView({ refreshKey = 0, onSelect }: Props) {
  const { getToken, orgId } = useAuth()
  const [scans, setScans] = useState<ScanSummary[] | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function load() {
    setLoading(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) {
        setError('Not signed in.')
        return
      }
      const resp = await listScans(token)
      setScans(resp.scans)
    } catch (e) {
      setError((e as Error).message || 'Could not load history.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
    // Reload when the parent bumps refreshKey (after an upload) and when the
    // active Clerk org changes (OrganizationSwitcher) — switching org changes
    // which scans /scans returns, so the list must refetch.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey, orgId])

  if (loading && !scans) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 text-center text-sm text-gray-400">
        Loading history…
      </div>
    )
  }

  if (error) {
    return (
      <div className="rounded-xl border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
        {error}
      </div>
    )
  }

  if (!scans || scans.length === 0) {
    return (
      <div className="rounded-xl border border-gray-200 bg-white p-5 text-center text-sm text-gray-400">
        No past scans yet. Upload a CV below to start your history.
      </div>
    )
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-gray-800">
          Recent scans <span className="text-xs font-normal text-gray-400">({scans.length})</span>
        </h3>
        <button
          onClick={load}
          className="text-xs text-blue-600 hover:underline disabled:opacity-50"
          disabled={loading}
        >
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      <ul className="space-y-2">
        {scans.map((s) => (
          <li key={s.scan_id}>
            <button
              type="button"
              onClick={() => onSelect?.(s.scan_id)}
              className="flex w-full items-center gap-3 rounded-lg border border-gray-100 bg-gray-50 px-3 py-2 text-left transition-colors hover:border-blue-300 hover:bg-blue-50"
            >
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-semibold ${RISK_PILL[s.risk_level]}`}
              >
                {s.risk_level}
              </span>
              <span className="grow truncate text-sm text-gray-800">{s.filename}</span>
              <span className="shrink-0 text-xs text-gray-400">{formatDate(s.created_at)}</span>
              <span className="shrink-0 text-xs text-gray-400">{s.risk_score}/100</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
