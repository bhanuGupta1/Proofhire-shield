import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { Link, useParams } from 'react-router-dom'
import { getCandidate, getScan, updateCandidate } from '../lib/api'
import type { Candidate, ScanResult } from '../lib/types'
import { OutreachComposer } from '../components/OutreachComposer'
import { OutcomeTracker } from '../components/OutcomeTracker'
import { RiskTab } from '../components/tabs/RiskTab'
import { MatchTab } from '../components/tabs/MatchTab'
import { ProofTab } from '../components/tabs/ProofTab'
import { AssessmentTab } from '../components/tabs/AssessmentTab'

const STATUSES = ['new', 'reviewing', 'shortlisted', 'rejected', 'hired']
type Tab = 'risk' | 'match' | 'proof' | 'assessment'
const TABS: { id: Tab; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'match', label: 'Match' },
  { id: 'proof', label: 'Proof' },
  { id: 'assessment', label: 'Assessment' },
]

export function CandidateDetail() {
  const { id } = useParams<{ id: string }>()
  const { getToken } = useAuth()
  const [candidate, setCandidate] = useState<Candidate | null>(null)
  const [scan, setScan] = useState<ScanResult | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('risk')
  const [notes, setNotes] = useState('')
  const [savingNotes, setSavingNotes] = useState(false)

  useEffect(() => {
    async function load() {
      if (!id) return
      setLoading(true)
      setError(null)
      try {
        const token = await getToken()
        if (!token) {
          setError('Sign in to view this candidate.')
          return
        }
        const c = await getCandidate(id, token)
        setCandidate(c)
        setNotes(c.notes ?? '')
        // Rehydrate the linked scan so the security tabs render in full.
        if (c.scan_id) {
          try {
            setScan(await getScan(c.scan_id, token))
          } catch {
            setScan(null) // scan may have been deleted; candidate survives.
          }
        }
      } catch (e) {
        setError((e as Error).message || 'Could not load candidate.')
      } finally {
        setLoading(false)
      }
    }
    void load()
  }, [id, getToken])

  async function changeStatus(next: string) {
    if (!candidate || !id) return
    const token = await getToken()
    if (!token) return
    const updated = await updateCandidate(id, { status: next }, token)
    setCandidate(updated)
  }

  async function saveNotes() {
    if (!id) return
    setSavingNotes(true)
    try {
      const token = await getToken()
      if (!token) return
      const updated = await updateCandidate(id, { notes }, token)
      setCandidate(updated)
    } finally {
      setSavingNotes(false)
    }
  }

  if (loading) {
    return <div className="py-16 text-center text-sm text-gray-400">Loading…</div>
  }
  if (error || !candidate) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error ?? 'Candidate not found.'}
        </div>
        <Link to="/candidates" className="text-sm text-blue-700 hover:underline">
          ← Back to candidates
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <Link to="/candidates" className="text-sm text-blue-700 hover:underline">
        ← Candidates
      </Link>

      {/* Header card */}
      <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <h2 className="text-xl font-bold tracking-tight text-gray-900">
              {candidate.full_name}
            </h2>
            {candidate.headline && (
              <p className="text-sm text-gray-500">{candidate.headline}</p>
            )}
            <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-gray-500">
              {candidate.email && <span>✉ {candidate.email}</span>}
              {candidate.phone && <span>☎ {candidate.phone}</span>}
              {candidate.location && <span>📍 {candidate.location}</span>}
              <span className="capitalize">Source: {candidate.source}</span>
            </div>
          </div>
          <div className="flex items-center gap-2">
            {candidate.risk_level && (
              <span className={`rounded-full px-2.5 py-1 text-xs font-bold tracking-wider
                ${candidate.risk_level === 'GREEN' ? 'bg-green-100 text-green-700' : ''}
                ${candidate.risk_level === 'ORANGE' ? 'bg-amber-100 text-amber-700' : ''}
                ${candidate.risk_level === 'RED' ? 'bg-red-100 text-red-700' : ''}`}
              >
                {candidate.risk_level}
              </span>
            )}
            <select
              value={candidate.status}
              onChange={(e) => void changeStatus(e.target.value)}
              className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm capitalize shadow-sm focus:border-blue-400 focus:outline-none"
            >
              {STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Notes */}
        <div className="mt-4">
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-gray-400">
            Notes
          </label>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            rows={3}
            placeholder="Private notes about this candidate…"
            className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
          />
          {notes !== (candidate.notes ?? '') && (
            <button
              onClick={saveNotes}
              disabled={savingNotes}
              className="mt-2 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-gray-700 disabled:opacity-60"
            >
              {savingNotes ? 'Saving…' : 'Save notes'}
            </button>
          )}
        </div>
      </div>

      {/* Security / intelligence tabs from the linked scan */}
      {scan ? (
        <div>
          <div className="mb-5 inline-flex gap-1 rounded-xl border border-gray-200 bg-white/80 p-1 shadow-sm">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`rounded-lg px-4 py-1.5 text-sm font-medium transition-all
                  ${activeTab === t.id
                    ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-sm'
                    : 'text-gray-600 hover:bg-gray-100 hover:text-gray-900'}`}
              >
                {t.label}
              </button>
            ))}
          </div>
          {activeTab === 'risk' && <RiskTab result={scan} />}
          {activeTab === 'match' && <MatchTab result={scan} />}
          {activeTab === 'proof' && <ProofTab result={scan} file={null} />}
          {activeTab === 'assessment' && (
            <AssessmentTab result={scan} billing={null} onUpgrade={() => {}} />
          )}
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 px-4 py-8 text-center text-sm text-gray-400">
          {candidate.scan_id
            ? 'The originating scan is no longer available.'
            : 'This candidate was added manually — no scan attached.'}
        </div>
      )}

      <OutcomeTracker candidateId={candidate.id} />
      <OutreachComposer candidateId={candidate.id} />
    </div>
  )
}
