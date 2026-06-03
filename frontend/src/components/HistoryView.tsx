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
    <div className="rounded-xl border border-gray-200 bg-white/80 p-5 shadow-sm backdrop-blur-sm">
      <div className="mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 ring-1 ring-gray-100">
            <svg className="h-3.5 w-3.5 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"/></svg>
          </div>
          <h3 className="text-sm font-semibold text-gray-800">
            Recent scans <span className="ml-0.5 text-xs font-medium text-gray-400">({scans.length})</span>
          </h3>
        </div>
        <button
          onClick={load}
          className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium text-blue-600 transition hover:bg-blue-50 disabled:opacity-50"
          disabled={loading}
        >
          <svg className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"/></svg>
          {loading ? 'Refreshing…' : 'Refresh'}
        </button>
      </div>
      <ul className="space-y-2">
        {scans.map((s) => (
          <li key={s.scan_id}>
            <button
              type="button"
              onClick={() => onSelect?.(s.scan_id)}
              className="group flex w-full items-center gap-3 rounded-lg border border-gray-100 bg-white px-3 py-2.5 text-left shadow-sm transition-all hover:-translate-y-0.5 hover:border-blue-200 hover:bg-blue-50/50 hover:shadow-md"
            >
              <span
                className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold tracking-wider ${RISK_PILL[s.risk_level]}`}
              >
                {s.risk_level}
              </span>
              <span className="grow truncate text-sm font-medium text-gray-800">{s.filename}</span>
              <span className="hidden shrink-0 text-xs text-gray-400 sm:inline">{formatDate(s.created_at)}</span>
              <span className="shrink-0 rounded-md bg-gray-50 px-1.5 py-0.5 text-xs font-medium text-gray-500 ring-1 ring-gray-100">{s.risk_score}/100</span>
              <svg className="h-4 w-4 shrink-0 text-gray-300 transition group-hover:translate-x-0.5 group-hover:text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7"/></svg>
            </button>
          </li>
        ))}
      </ul>
    </div>
  )
}
