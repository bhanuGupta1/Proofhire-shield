import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { getJob, updateJob } from '../lib/api'
import type { Job } from '../lib/types'
import { PipelineBoard } from '../components/PipelineBoard'
import { ShortlistPanel } from '../components/ShortlistPanel'

const STATUSES = ['open', 'on_hold', 'closed', 'filled']

export function JobDetail() {
  const { id } = useParams<{ id: string }>()
  const { getToken } = useAuth()
  const navigate = useNavigate()
  const [job, setJob] = useState<Job | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      if (!id) return
      try {
        const token = await getToken()
        if (!token) {
          setError('Sign in to view this job.')
          return
        }
        setJob(await getJob(id, token))
      } catch (e) {
        setError((e as Error).message || 'Could not load job.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [id, getToken])

  async function changeStatus(next: string) {
    if (!id) return
    const token = await getToken()
    if (!token) return
    setJob(await updateJob(id, { status: next }, token))
  }

  if (loading) {
    return <div className="py-16 text-center text-sm text-gray-400">Loading…</div>
  }
  if (error || !job) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error ?? 'Job not found.'}
        </div>
        <Link to="/jobs" className="text-sm text-blue-700 hover:underline">
          ← Back to jobs
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/jobs" className="text-sm text-blue-700 hover:underline">
        ← Jobs
      </Link>

      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-bold tracking-tight text-gray-900">{job.title}</h2>
            <div className="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
              {job.client_name && <span>Client: {job.client_name}</span>}
              {job.location && <span>📍 {job.location}</span>}
              {job.employment_type && <span>{job.employment_type}</span>}
              {job.seniority && <span>{job.seniority}</span>}
            </div>
          </div>
          <div className="flex items-center gap-2">
            <select
              value={job.status}
              onChange={(e) => void changeStatus(e.target.value)}
              className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm capitalize shadow-sm focus:border-blue-400 focus:outline-none"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s.replace('_', ' ')}
                </option>
              ))}
            </select>
            <button
              onClick={() => navigate(`/jobs/${job.id}/edit`)}
              className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
            >
              Edit
            </button>
          </div>
        </div>

        {job.required_skills.length > 0 && (
          <div className="mt-4">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Required skills
            </p>
            <div className="flex flex-wrap gap-1.5">
              {job.required_skills.map((s) => (
                <span key={s} className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
                  {s}
                </span>
              ))}
            </div>
          </div>
        )}

        {job.description && (
          <div className="mt-4">
            <p className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Description
            </p>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-gray-600">
              {job.description}
            </p>
          </div>
        )}
      </div>

      <PipelineBoard jobId={job.id} />

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <ShortlistPanel jobId={job.id} />
        {/* Matched candidates lands in Phase 3 (semantic matching). */}
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 p-5 text-center">
          <p className="text-sm font-medium text-gray-500">Matched candidates</p>
          <p className="mt-1 text-xs text-gray-400">Semantic matching — coming soon.</p>
        </div>
      </div>
    </div>
  )
}
