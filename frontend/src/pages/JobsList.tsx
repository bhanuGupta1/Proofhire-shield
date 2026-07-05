import { useEffect, useState } from 'react'
import { useAuth, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import { listJobs } from '../lib/api'
import type { Job } from '../lib/types'

function StatusPill({ status }: { status: string }) {
  const cls =
    status === 'open'
      ? 'bg-green-100 text-green-700'
      : status === 'filled'
        ? 'bg-blue-100 text-blue-700'
        : status === 'closed'
          ? 'bg-gray-200 text-gray-600'
          : 'bg-amber-100 text-amber-700'
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${cls}`}>
      {status.replace('_', ' ')}
    </span>
  )
}

function JobsInner() {
  const { getToken } = useAuth()
  const [jobs, setJobs] = useState<Job[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      try {
        const token = await getToken()
        if (!token) {
          setError('Sign in to view jobs.')
          return
        }
        const res = await listJobs(token)
        setJobs(res.jobs)
      } catch (e) {
        setError((e as Error).message || 'Could not load jobs.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [getToken])

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="text-xl font-bold tracking-tight text-gray-900">Jobs</h2>
          <p className="text-sm text-gray-500">Roles you're filling.</p>
        </div>
        <Link
          to="/jobs/new"
          className="rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:opacity-90"
        >
          + New job
        </Link>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {loading ? (
        <div className="py-16 text-center text-sm text-gray-400">Loading…</div>
      ) : jobs.length === 0 ? (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">No jobs yet</p>
          <p className="mt-1 text-xs text-gray-400">Create your first role to start matching candidates.</p>
          <Link
            to="/jobs/new"
            className="mt-4 inline-block rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm"
          >
            + New job
          </Link>
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-gray-200 bg-white shadow-sm">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-gray-100 bg-gray-50/60 text-xs uppercase tracking-wide text-gray-400">
              <tr>
                <th className="px-4 py-3 font-semibold">Title</th>
                <th className="px-4 py-3 font-semibold">Client</th>
                <th className="px-4 py-3 font-semibold">Location</th>
                <th className="px-4 py-3 font-semibold">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {jobs.map((j) => (
                <tr key={j.id} className="transition hover:bg-blue-50/40">
                  <td className="px-4 py-3">
                    <Link to={`/jobs/${j.id}`} className="font-medium text-blue-700 hover:underline">
                      {j.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-gray-500">{j.client_name ?? '—'}</td>
                  <td className="px-4 py-3 text-gray-500">{j.location ?? '—'}</td>
                  <td className="px-4 py-3">
                    <StatusPill status={j.status} />
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

export function JobsList() {
  return (
    <>
      <SignedIn>
        <JobsInner />
      </SignedIn>
      <SignedOut>
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">Sign in to manage jobs</p>
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
