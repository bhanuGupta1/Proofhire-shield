import { useState } from 'react'
import { useAuth, SignedIn, SignedOut, SignInButton } from '@clerk/clerk-react'
import { importCandidates, importJobs } from '../lib/api'
import { parseCsv } from '../lib/csv'
import type { ImportResult } from '../lib/types'

type Kind = 'candidates' | 'jobs'

const SAMPLE: Record<Kind, string> = {
  candidates: 'full_name,email,headline,location\nAda Lovelace,ada@example.com,Data Engineer,London',
  jobs: 'title,client_name,location,skills\nBackend Engineer,Acme,Remote,"python, fastapi"',
}

function ImportInner() {
  const { getToken } = useAuth()
  const [kind, setKind] = useState<Kind>('candidates')
  const [text, setText] = useState('')
  const [result, setResult] = useState<ImportResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const rows = text.trim() ? parseCsv(text) : []

  async function run() {
    if (rows.length === 0) return
    setBusy(true)
    setError(null)
    setResult(null)
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to import.')
        return
      }
      const res =
        kind === 'candidates'
          ? await importCandidates(rows, token)
          : await importJobs(rows, token)
      setResult(res)
    } catch (e) {
      setError((e as Error).message || 'Import failed.')
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="space-y-5">
      <div>
        <h2 className="text-xl font-bold tracking-tight text-gray-900">Import</h2>
        <p className="text-sm text-gray-500">
          Paste CSV to bring an existing book of candidates or jobs into ProofHire.
          Duplicates are skipped automatically.
        </p>
      </div>

      <div className="flex gap-1 rounded-lg border border-gray-200 bg-white p-1 shadow-sm w-fit">
        {(['candidates', 'jobs'] as Kind[]).map((k) => (
          <button
            key={k}
            onClick={() => {
              setKind(k)
              setResult(null)
            }}
            className={`rounded-md px-4 py-1.5 text-sm font-medium capitalize transition ${
              kind === k
                ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-sm'
                : 'text-gray-600 hover:bg-gray-100'
            }`}
          >
            {k}
          </button>
        ))}
      </div>

      <div className="rounded-xl border border-gray-200 bg-white p-4 shadow-sm">
        <div className="mb-2 flex items-center justify-between">
          <label className="text-xs font-semibold uppercase tracking-wide text-gray-400">
            CSV data
          </label>
          <button
            onClick={() => setText(SAMPLE[kind])}
            className="text-xs font-medium text-blue-600 hover:underline"
          >
            Insert sample
          </button>
        </div>
        <textarea
          value={text}
          onChange={(e) => {
            setText(e.target.value)
            setResult(null)
          }}
          rows={8}
          placeholder={SAMPLE[kind]}
          className="w-full rounded-lg border border-gray-300 bg-white px-3 py-2 font-mono text-xs shadow-sm focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
        <div className="mt-3 flex items-center justify-between">
          <span className="text-xs text-gray-400">
            {rows.length > 0 ? `${rows.length} row(s) parsed` : 'Header row required'}
          </span>
          <button
            onClick={() => void run()}
            disabled={rows.length === 0 || busy}
            className="rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition hover:opacity-90 disabled:opacity-50"
          >
            {busy ? 'Importing…' : `Import ${kind}`}
          </button>
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {result && (
        <div className="grid grid-cols-3 gap-3">
          <div className="rounded-xl border border-green-200 bg-green-50 p-4 text-center">
            <p className="text-2xl font-bold text-green-700">{result.created}</p>
            <p className="text-xs text-green-600">Created</p>
          </div>
          <div className="rounded-xl border border-amber-200 bg-amber-50 p-4 text-center">
            <p className="text-2xl font-bold text-amber-700">{result.skipped}</p>
            <p className="text-xs text-amber-600">Skipped (dupes)</p>
          </div>
          <div className="rounded-xl border border-gray-200 bg-gray-50 p-4 text-center">
            <p className="text-2xl font-bold text-gray-500">{result.invalid}</p>
            <p className="text-xs text-gray-400">Invalid</p>
          </div>
        </div>
      )}
    </div>
  )
}

export function ImportWizard() {
  return (
    <>
      <SignedIn>
        <ImportInner />
      </SignedIn>
      <SignedOut>
        <div className="rounded-xl border border-dashed border-gray-300 bg-white/60 py-16 text-center">
          <p className="text-sm font-medium text-gray-600">Sign in to import data</p>
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
