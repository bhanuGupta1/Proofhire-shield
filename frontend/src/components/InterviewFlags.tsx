import { useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { interviewFlags } from '../lib/api'
import type { FlagSummary } from '../lib/types'

// Ad-hoc interview-notes → red/green flag summariser. Stateless: nothing is
// stored; paste notes, read the flags, copy what's useful into the candidate's
// outcome notes.
export function InterviewFlags() {
  const { getToken } = useAuth()
  const [notes, setNotes] = useState('')
  const [summary, setSummary] = useState<FlagSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function analyse() {
    if (!notes.trim()) return
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      setSummary(await interviewFlags(notes.trim(), token))
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-gray-500">
        Interview flag summary
      </h3>

      {error && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      <textarea
        value={notes}
        onChange={(e) => setNotes(e.target.value)}
        rows={4}
        placeholder="Paste raw interview notes — I'll pull out green flags, red flags, and a recommended next step…"
        className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
      />
      <button
        onClick={() => void analyse()}
        disabled={!notes.trim() || busy}
        className="mt-2 rounded-lg bg-gray-900 px-4 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-gray-700 disabled:opacity-50"
      >
        {busy ? 'Analysing…' : 'Summarise'}
      </button>

      {summary && (
        <div className="mt-4 space-y-3">
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-green-100 bg-green-50/50 p-3">
              <p className="mb-1.5 text-xs font-semibold text-green-700">Green flags</p>
              {summary.green_flags.length === 0 ? (
                <p className="text-xs text-gray-400">None detected.</p>
              ) : (
                <ul className="list-disc space-y-1 pl-4 text-xs text-gray-600">
                  {summary.green_flags.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-lg border border-red-100 bg-red-50/50 p-3">
              <p className="mb-1.5 text-xs font-semibold text-red-700">Red flags</p>
              {summary.red_flags.length === 0 ? (
                <p className="text-xs text-gray-400">None detected.</p>
              ) : (
                <ul className="list-disc space-y-1 pl-4 text-xs text-gray-600">
                  {summary.red_flags.map((f, i) => (
                    <li key={i}>{f}</li>
                  ))}
                </ul>
              )}
            </div>
          </div>
          <div className="rounded-lg bg-blue-50/60 px-3 py-2 text-xs">
            <span className="font-semibold text-blue-700">Recommended: </span>
            <span className="text-gray-700">{summary.recommended_step}</span>
          </div>
        </div>
      )}
    </div>
  )
}
