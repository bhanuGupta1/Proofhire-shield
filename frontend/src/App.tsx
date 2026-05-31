import { useState } from 'react'
import {
  ClerkProvider,
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
  useAuth,
} from '@clerk/clerk-react'
import { FileUpload } from './components/FileUpload'
import { RiskTab } from './components/tabs/RiskTab'
import { MatchTab } from './components/tabs/MatchTab'
import { ProofTab } from './components/tabs/ProofTab'
import { AssessmentTab } from './components/tabs/AssessmentTab'
import { JDMatcher } from './components/JDMatcher'
import { scanCV } from './lib/api'
import type { ScanResult } from './lib/types'

const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined

type Tab = 'risk' | 'match' | 'proof' | 'assessment'

const TABS: { id: Tab; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'match', label: 'Match' },
  { id: 'proof', label: 'Proof' },
  { id: 'assessment', label: 'Assessment' },
]


function AppContent() {
  const { getToken, isSignedIn } = useAuth()
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
      const token = isSignedIn ? await getToken() : null
      const resp = await scanCV(f, token)
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
      <header className="border-b border-gray-200 bg-white px-6 py-4">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="text-2xl">🛡️</span>
            <div>
              <h1 className="text-lg font-bold leading-none text-gray-900">ProofHire Shield</h1>
              <p className="text-xs text-gray-500">Candidate intelligence — secure by design</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <SignedOut>
              <SignInButton mode="modal">
                <button className="rounded-lg border border-gray-300 px-3 py-1.5 text-sm font-medium text-gray-700 hover:bg-gray-100">
                  Sign in
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <span className="text-xs text-gray-400">History enabled</span>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        <FileUpload onFile={handleFile} loading={loading} />

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && file && (
          <div>
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

            {activeTab === 'risk' && <RiskTab result={result} />}
            {activeTab === 'match' && <MatchTab result={result} />}
            {activeTab === 'proof' && <ProofTab result={result} file={file} />}
            {activeTab === 'assessment' && <AssessmentTab result={result} />}

            <div className="mt-8">
              <JDMatcher cvText={result.safe_copy_text} />
            </div>
          </div>
        )}
      </main>
    </div>
  )
}


export default function App() {
  if (!CLERK_KEY) {
    // Clerk not configured — render a clear error so the operator notices.
    // We don't fall back to the anonymous UI silently because that would
    // ship a "demo" build that quietly omits the history feature.
    return (
      <div className="flex min-h-screen items-center justify-center bg-gray-50 p-6">
        <div className="max-w-md rounded-lg border border-amber-200 bg-amber-50 p-5 text-sm text-amber-800">
          <p className="font-semibold mb-2">Authentication is not configured.</p>
          <p>
            Set <code className="font-mono">VITE_CLERK_PUBLISHABLE_KEY</code> in the
            build environment and redeploy.
          </p>
        </div>
      </div>
    )
  }
  return (
    <ClerkProvider publishableKey={CLERK_KEY}>
      <AppContent />
    </ClerkProvider>
  )
}
