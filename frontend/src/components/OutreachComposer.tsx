import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { draftOutreach, listOutreach, logOutreach } from '../lib/api'
import type { OutreachMessage } from '../lib/types'

export function OutreachComposer({ candidateId }: { candidateId: string }) {
  const { getToken } = useAuth()
  const [history, setHistory] = useState<OutreachMessage[]>([])
  const [subject, setSubject] = useState('')
  const [body, setBody] = useState('')
  const [channel, setChannel] = useState('email')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function refresh() {
    try {
      const token = await getToken()
      if (!token) return
      setHistory(await listOutreach(candidateId, token))
    } catch (e) {
      setError((e as Error).message)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [candidateId])

  async function draft() {
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      const d = await draftOutreach(candidateId, token)
      setSubject(d.subject)
      setBody(d.body)
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function log() {
    if (!body.trim()) return
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      await logOutreach(
        candidateId,
        { channel, subject: subject.trim() || undefined, body: body.trim() },
        token,
      )
      setSubject('')
      setBody('')
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  const field =
    'w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400'

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Outreach
        </h3>
        <button
          onClick={() => void draft()}
          disabled={busy}
          className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 transition hover:bg-blue-100 disabled:opacity-50"
        >
          ✨ Draft message
        </button>
      </div>

      {error && (
        <div className="mb-2 rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="space-y-2">
        <div className="flex gap-2">
          <select
            value={channel}
            onChange={(e) => setChannel(e.target.value)}
            className="rounded-lg border border-gray-300 bg-white px-2 py-2 text-sm shadow-sm focus:border-blue-400 focus:outline-none"
          >
            <option value="email">Email</option>
            <option value="call">Call</option>
            <option value="note">Note</option>
          </select>
          <input
            value={subject}
            onChange={(e) => setSubject(e.target.value)}
            placeholder="Subject (optional)"
            className={field}
          />
        </div>
        <textarea
          value={body}
          onChange={(e) => setBody(e.target.value)}
          rows={5}
          placeholder="Write or draft a message, then log it once sent…"
          className={field}
        />
        <button
          onClick={() => void log()}
          disabled={!body.trim() || busy}
          className="rounded-lg bg-gray-900 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:bg-gray-700 disabled:opacity-50"
        >
          Log outreach
        </button>
      </div>

      {history.length > 0 && (
        <div className="mt-5 border-t border-gray-100 pt-4">
          <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
            History
          </p>
          <ul className="space-y-3">
            {history.map((m) => (
              <li key={m.id} className="rounded-lg border border-gray-100 bg-gray-50/60 p-3">
                <div className="mb-1 flex items-center gap-2 text-xs text-gray-400">
                  <span className="rounded-full bg-gray-200 px-2 py-0.5 font-medium capitalize text-gray-600">
                    {m.channel}
                  </span>
                  {m.subject && <span className="font-medium text-gray-600">{m.subject}</span>}
                  <span className="ml-auto">
                    {new Date(m.created_at).toLocaleDateString()}
                  </span>
                </div>
                <p className="whitespace-pre-wrap text-xs leading-relaxed text-gray-600">
                  {m.body}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  )
}
