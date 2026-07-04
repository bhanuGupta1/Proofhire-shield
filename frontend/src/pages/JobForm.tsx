import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { useNavigate, useParams } from 'react-router-dom'
import { createJob, getJob, updateJob } from '../lib/api'

function skillsToText(skills: string[]): string {
  return skills.join(', ')
}
function textToSkills(text: string): string[] {
  return text
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean)
}

export function JobForm() {
  const { id } = useParams<{ id: string }>()
  const editing = Boolean(id)
  const { getToken } = useAuth()
  const navigate = useNavigate()

  const [title, setTitle] = useState('')
  const [clientName, setClientName] = useState('')
  const [location, setLocation] = useState('')
  const [employmentType, setEmploymentType] = useState('')
  const [seniority, setSeniority] = useState('')
  const [description, setDescription] = useState('')
  const [skillsText, setSkillsText] = useState('')
  const [loading, setLoading] = useState(editing)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    async function load() {
      if (!id) return
      try {
        const token = await getToken()
        if (!token) {
          setError('Sign in to edit jobs.')
          return
        }
        const job = await getJob(id, token)
        setTitle(job.title)
        setClientName(job.client_name ?? '')
        setLocation(job.location ?? '')
        setEmploymentType(job.employment_type ?? '')
        setSeniority(job.seniority ?? '')
        setDescription(job.description)
        setSkillsText(skillsToText(job.required_skills))
      } catch (e) {
        setError((e as Error).message)
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [id, getToken])

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSaving(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to save jobs.')
        return
      }
      const payload = {
        title: title.trim(),
        client_name: clientName.trim() || undefined,
        location: location.trim() || undefined,
        employment_type: employmentType.trim() || undefined,
        seniority: seniority.trim() || undefined,
        description: description.trim(),
        required_skills: textToSkills(skillsText),
      }
      const job = editing
        ? await updateJob(id as string, payload, token)
        : await createJob(payload, token)
      navigate(`/jobs/${job.id}`)
    } catch (e) {
      setError((e as Error).message || 'Could not save job.')
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return <div className="py-16 text-center text-sm text-gray-400">Loading…</div>
  }

  const field =
    'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400'
  const label = 'mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-400'

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <h2 className="text-xl font-bold tracking-tight text-gray-900">
        {editing ? 'Edit job' : 'New job'}
      </h2>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4 rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div>
          <label className={label}>Title *</label>
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            required
            placeholder="e.g. Senior Backend Engineer"
            className={field}
          />
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <div>
            <label className={label}>Client</label>
            <input value={clientName} onChange={(e) => setClientName(e.target.value)} className={field} />
          </div>
          <div>
            <label className={label}>Location</label>
            <input value={location} onChange={(e) => setLocation(e.target.value)} className={field} />
          </div>
          <div>
            <label className={label}>Employment type</label>
            <input
              value={employmentType}
              onChange={(e) => setEmploymentType(e.target.value)}
              placeholder="e.g. Full-time"
              className={field}
            />
          </div>
          <div>
            <label className={label}>Seniority</label>
            <input
              value={seniority}
              onChange={(e) => setSeniority(e.target.value)}
              placeholder="e.g. Senior"
              className={field}
            />
          </div>
        </div>
        <div>
          <label className={label}>Required skills (comma-separated)</label>
          <input
            value={skillsText}
            onChange={(e) => setSkillsText(e.target.value)}
            placeholder="python, fastapi, postgres"
            className={field}
          />
        </div>
        <div>
          <label className={label}>Description</label>
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            rows={6}
            className={field}
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            type="submit"
            disabled={saving || !title.trim()}
            className="rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:opacity-90 disabled:opacity-60"
          >
            {saving ? 'Saving…' : editing ? 'Save changes' : 'Create job'}
          </button>
          <button
            type="button"
            onClick={() => navigate(editing ? `/jobs/${id}` : '/jobs')}
            className="rounded-lg border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm transition hover:bg-gray-50"
          >
            Cancel
          </button>
        </div>
      </form>
    </div>
  )
}
