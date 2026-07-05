import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { listCandidateOutcomes, listJobs, recordOutcome } from '../lib/api'
import type { Job, Outcome, OutcomeType } from '../lib/types'

const TYPES: OutcomeType[] = [
  'interviewed',
  'offered',
  'hired',
  'rejected',
  'withdrawn',
  'placed',
]

const TYPE_CLASS: Record<string, string> = {
  interviewed: 'bg-blue-100 text-blue-700',
  offered: 'bg-purple-100 text-purple-700',
  hired: 'bg-green-100 text-green-700',
  placed: 'bg-green-100 text-green-700',
  rejected: 'bg-gray-200 text-gray-600',
  withdrawn: 'bg-amber-100 text-amber-700',
}

export function OutcomeTracker({ candidateId }: { candidateId: string }) {
  const { getToken } = useAuth()
  const [outcomes, setOutcomes] = useState<Outcome[]>([])
  const [jobs, setJobs] = useState<Job[]>([])
  const [jobId, setJobId] = useState('')
  const [type, setType] = useState<OutcomeType>('interviewed')
  const [notes, setNotes] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    try {
      const token = await getToken()
      if (!token) return
      const [os, js] = await Promise.all([
        listCandidateOutcomes(candidateId, token),
        listJobs(token),
      ])
      setOutcomes(os)
      setJobs(js.jobs)
      if (!jobId && js.jobs.length > 0) setJobId(js.jobs[0].id)
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId])

  async function record() {
    if (!jobId) return
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      await recordOutcome(candidateId, { job_id: jobId, type, notes: notes.trim() || undefined }, token)
      setNotes('')
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const jobTitle = (id: string) => jobs.find((j) => j.id === id)?.title ?? 'a job'

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Outcomes
      </h3>

      {error && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      {jobs.length === 0 ? (
        <p className="text-xs text-gray-400">Create a job to record outcomes against it.</p>
      ) : (
        <div className="flex flex-wrap items-center gap-2">
          <select
            value={jobId}
            onChange={(e) => setJobId(e.target.value)}
            className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-blue-400 focus:outline-none"
          >
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                {j.title}
              </option>
            ))}
          </select>
          <select
            value={type}
            onChange={(e) => setType(e.target.value as OutcomeType)}
            className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs capitalize shadow-sm focus:border-blue-400 focus:outline-none"
          >
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {t}
              </option>
            ))}
          </select>
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Note (optional)"
            className="grow rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-blue-400 focus:outline-none"
          />
          <button
            onClick={() => void record()}
            disabled={busy || !jobId}
            className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-gray-700 disabled:opacity-50"
          >
            Record
          </button>
        </div>
      )}

      {outcomes.length > 0 && (
        <ul className="mt-4 space-y-2">
          {outcomes.map((o) => (
            <li key={o.id} className="flex items-center gap-2 text-xs">
              <span className={`rounded-full px-2 py-0.5 font-semibold capitalize ${TYPE_CLASS[o.type] ?? 'bg-gray-100 text-gray-600'}`}>
                {o.type}
              </span>
              <span className="text-gray-500">on {jobTitle(o.job_id)}</span>
              {o.notes && <span className="text-gray-400">— {o.notes}</span>}
              <span className="ml-auto text-gray-300">
                {new Date(o.occurred_at).toLocaleDateString()}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
