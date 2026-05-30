import { useState } from 'react'
import { FileUpload } from './components/FileUpload'
import { RiskTab } from './components/tabs/RiskTab'
import { MatchTab } from './components/tabs/MatchTab'
import { ProofTab } from './components/tabs/ProofTab'
import { JDMatcher } from './components/JDMatcher'
import { scanCV } from './lib/api'
import type { ScanResult } from './lib/types'

type Tab = 'risk' | 'match' | 'proof'

const TABS: { id: Tab; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'match', label: 'Match' },
  { id: 'proof', label: 'Proof' },
]

export default function App() {
  const [result, setResult] = useState<ScanResult | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('risk')

  async function handleFile(f: File) {
    setFile(f)
    setError(null)
    setLoading(true)
    try {
      const resp = await scanCV(f)
      if (!resp.ok || !resp.result) {
        setError(resp.error ?? 'Scan failed')
      } else {
        setResult(resp.result)
        setActiveTab('risk')
      }
    } catch {
      setError('Could not reach the scan service. Is the backend running?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center gap-3">
          <span className="text-2xl">🛡️</span>
          <div>
            <h1 className="text-lg font-bold leading-none text-gray-900">ProofHire Shield</h1>
            <p className="text-xs text-gray-500">Candidate intelligence — secure by design</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        {/* Upload */}
        <FileUpload onFile={handleFile} loading={loading} />

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && file && (
          <div>
            {/* Tabs */}
            <div className="mb-6 flex gap-1 border-b border-gray-200">
              {TABS.map((t) => (
                <button
                  key={t.id}
                  onClick={() => setActiveTab(t.id)}
                  className={`px-4 py-2 text-sm font-medium transition-colors
                    ${activeTab === t.id
                      ? 'border-b-2 border-blue-600 text-blue-600'
                      : 'text-gray-500 hover:text-gray-700'}`}
                >
                  {t.label}
                </button>
              ))}
            </div>

            {/* Tab content */}
            {activeTab === 'risk' && <RiskTab result={result} />}
            {activeTab === 'match' && <MatchTab result={result} />}
            {activeTab === 'proof' && <ProofTab result={result} file={file} />}

            {/* JD matcher — always visible below the tabs */}
            <div className="mt-8">
              <JDMatcher cvText={result.safe_copy_text} />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}
