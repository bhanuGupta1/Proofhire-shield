import { useEffect, useState } from 'react'
import { useAuth, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import { getDashboardMetrics, getTenantFunnel, getToday } from '../lib/api'
import type {
  DashboardMetrics,
  Funnel,
  MiniCandidate,
  TodayQueue,
} from '../lib/types'

const FUNNEL_ORDER = ['interviewed', 'offered', 'hired', 'placed', 'rejected', 'withdrawn']

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
      <p className="text-2xl font-bold tracking-tight text-gray-900">{value}</p>
      <p className="text-xs text-gray-500">{label}</p>
    </div>
  )
}

function RiskBar({ risk }: { risk: DashboardMetrics['risk'] }) {
  const total = risk.GREEN + risk.ORANGE + risk.RED
  if (total === 0) {
    return <p className="text-xs text-gray-400">No scans yet.</p>
  }
  const seg = (n: number, cls: string) =>
    n > 0 ? <div className={cls} style={{ width: `${(n / total) * 100}%` }} /> : null
  return (
    <div>
      <div className="flex h-3 overflow-hidden rounded-full bg-gray-100">
        {seg(risk.GREEN, 'bg-green-500')}
        {seg(risk.ORANGE, 'bg-amber-500')}
        {seg(risk.RED, 'bg-red-500')}
      </div>
      <div className="mt-2 flex gap-4 text-xs text-gray-500">
        <span><span className="font-semibold text-green-600">{risk.GREEN}</span> green</span>
        <span><span className="font-semibold text-amber-600">{risk.ORANGE}</span> elevated</span>
        <span><span className="font-semibold text-red-600">{risk.RED}</span> high-risk</span>
      </div>
    </div>
  )
}

function MiniCandRow({ c }: { c: MiniCandidate }) {
  return (
    <li className="flex items-center justify-between py-1.5">
      <Link to={`/candidates/${c.id}`} className="text-sm text-blue-700 hover:underline">
        {c.full_name}
      </Link>
      {c.risk_level === 'RED' && (
        <span className="rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-bold text-red-700">
          RED
        </span>
      )}
    </li>
  )
}

function DashboardInner() {
  const { getToken } = useAuth()
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [today, setToday] = useState<TodayQueue | null>(null)
  const [funnel, setFunnel] = useState<Funnel | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const token = await getToken()
        if (!token) {
          setError('Sign in to view your dashboard.')
          return
        }
        const [m, t, f] = await Promise.all([
          getDashboardMetrics(token),
          getToday(token),
          getTenantFunnel(token),
        ])
        setMetrics(m)
        setToday(t)
        setFunnel(f)
      } catch (e) {
        setError((e as Error).message || 'Could not load dashboard.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [getToken])

  if (loading) {
    return <div className="py-16 text-center text-sm text-gray-400">Loading…</div>
  }
  if (error || !metrics || !today) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
        {error ?? 'Could not load dashboard.'}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-gray-900">Dashboard</h2>
        <p className="text-sm text-gray-500">Your recruiting at a glance.</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <Stat label="Candidates" value={metrics.candidates_total} />
        <Stat label="Jobs" value={metrics.jobs_total} />
        <Stat label="Open jobs" value={metrics.open_jobs} />
        <Stat label="In pipeline" value={metrics.placements_total} />
        <Stat label="Shortlisted" value={metrics.shortlist_total} />
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          CV risk distribution
        </h3>
        <RiskBar risk={metrics.risk} />
      </div>

      {funnel && (
        <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
              Conversion funnel
            </h3>
            <span className="text-xs text-gray-400">
              <span className="font-bold text-green-600">{funnel.placed}</span> placed ·{' '}
              {funnel.total} outcomes
            </span>
          </div>
          {funnel.total === 0 ? (
            <p className="text-xs text-gray-400">
              Record outcomes on candidates to track your placement funnel.
            </p>
          ) : (
            <div className="grid grid-cols-3 gap-2 sm:grid-cols-6">
              {FUNNEL_ORDER.map((t) => (
                <div key={t} className="rounded-lg bg-gray-50 p-2 text-center">
                  <p className="text-lg font-bold text-gray-800">{funnel.counts[t] ?? 0}</p>
                  <p className="text-[10px] capitalize text-gray-400">{t}</p>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Today queue */}
      <div>
        <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
          Today
        </h3>
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-gray-700">
              New candidates{' '}
              <span className="text-gray-400">({today.new_candidates_count})</span>
            </p>
            {today.new_candidates.length === 0 ? (
              <p className="text-xs text-gray-400">Nothing new to review.</p>
            ) : (
              <ul className="divide-y divide-gray-50">
                {today.new_candidates.map((c) => (
                  <MiniCandRow key={c.id} c={c} />
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-gray-700">
              High-risk CVs{' '}
              <span className="text-gray-400">({today.high_risk_count})</span>
            </p>
            {today.high_risk_candidates.length === 0 ? (
              <p className="text-xs text-gray-400">No high-risk candidates.</p>
            ) : (
              <ul className="divide-y divide-gray-50">
                {today.high_risk_candidates.map((c) => (
                  <MiniCandRow key={c.id} c={c} />
                ))}
              </ul>
            )}
          </div>

          <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
            <p className="mb-2 text-sm font-semibold text-gray-700">
              Open jobs, no candidates{' '}
              <span className="text-gray-400">
                ({today.open_jobs_without_candidates_count})
              </span>
            </p>
            {today.open_jobs_without_candidates.length === 0 ? (
              <p className="text-xs text-gray-400">Every open job has candidates.</p>
            ) : (
              <ul className="divide-y divide-gray-50">
                {today.open_jobs_without_candidates.map((j) => (
                  <li key={j.id} className="py-1.5">
                    <Link to={`/jobs/${j.id}`} className="text-sm text-blue-700 hover:underline">
                      {j.title}
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}

export function Dashboard() {
  return (
    <>
      <SignedIn>
        <DashboardInner />
      </SignedIn>
      <SignedOut>
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">Sign in to see your dashboard</p>
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
