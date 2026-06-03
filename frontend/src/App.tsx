import { useState, useEffect } from 'react'
import {
  ClerkProvider,
  OrganizationSwitcher,
  SignedIn,
  SignedOut,
  SignInButton,
  UserButton,
  useAuth,
} from '@clerk/clerk-react'
import { FileUpload } from './components/FileUpload'
import { HistoryView } from './components/HistoryView'
import { RiskTab } from './components/tabs/RiskTab'
import { MatchTab } from './components/tabs/MatchTab'
import { ProofTab } from './components/tabs/ProofTab'
import { AssessmentTab } from './components/tabs/AssessmentTab'
import { JDMatcher } from './components/JDMatcher'
import { QuotaMeter } from './components/QuotaMeter'
import { PricingModal } from './components/PricingModal'
import { scanCV, getScan, getBillingStatus, startCheckout, openBillingPortal } from './lib/api'
import type { ScanResult, BillingStatus } from './lib/types'

const CLERK_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY as string | undefined

type Tab = 'risk' | 'match' | 'proof' | 'assessment'

const TABS: { id: Tab; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'match', label: 'Match' },
  { id: 'proof', label: 'Proof' },
  { id: 'assessment', label: 'Assessment' },
]


function AppContent() {
  const { getToken, isSignedIn, orgId, orgRole } = useAuth()
  // Phase 8.7 — orgRole comes from the Clerk session for the active org and
  // gates the "Upgrade Firm" button. "org:admin" is Clerk's canonical admin
  // role; we accept either that or a plain "admin" for forward-compat.
  const isOrgAdmin =
    Boolean(orgId) && (orgRole === 'org:admin' || orgRole === 'admin')

  const [result, setResult] = useState<ScanResult | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('risk')
  // Bumped after every successful authed scan so HistoryView re-fetches.
  const [historyKey, setHistoryKey] = useState(0)
  const [billing, setBilling] = useState<BillingStatus | null>(null)
  const [pricingOpen, setPricingOpen] = useState(false)
  const [checkoutBusy, setCheckoutBusy] = useState(false)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)

  async function refreshBilling() {
    if (!isSignedIn) {
      setBilling(null)
      return
    }
    try {
      const token = await getToken()
      if (!token) return
      setBilling(await getBillingStatus(token))
    } catch {
      // No database / billing unconfigured / offline — hide the meter rather
      // than block the scan flow. Mirrors the backend's degrade-open posture.
      setBilling(null)
    }
  }

  useEffect(() => {
    void refreshBilling()
  }, [isSignedIn])

  async function handleCheckout(scope: 'user' | 'org' = 'user') {
    setCheckoutBusy(true)
    setCheckoutError(null)
    try {
      const token = await getToken()
      if (!token) {
        setCheckoutError('Please sign in to upgrade.')
        return
      }
      window.location.href = await startCheckout(token, scope)
    } catch (e) {
      setCheckoutError((e as Error).message)
    } finally {
      setCheckoutBusy(false)
    }
  }

  async function handleManage(scope: 'user' | 'org' = 'user') {
    try {
      const token = await getToken()
      if (!token) return
      window.location.href = await openBillingPortal(token, scope)
    } catch (e) {
      setError((e as Error).message)
    }
  }

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
        // Only nudge HistoryView when the backend actually persisted (scan_id set).
        if (resp.result.scan_id) {
          setHistoryKey((k) => k + 1)
        }
      }
    } catch {
      setError('Could not reach the scan service. Is the backend running?')
    } finally {
      setLoading(false)
      void refreshBilling()
    }
  }

  async function handleSelectScan(scanId: string) {
    setError(null)
    setLoading(true)
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to open a saved scan.')
        return
      }
      const r = await getScan(scanId, token)
      setResult(r)
      setFile(null)
      setActiveTab('risk')
    } catch {
      setError('Could not open that scan.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen">
      <header className="sticky top-0 z-40 border-b border-gray-200/70 bg-white/75 px-6 py-4 backdrop-blur-md">
        <div className="mx-auto flex max-w-5xl items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-gradient-to-br from-blue-500 to-blue-700 shadow-sm">
              <svg className="h-5 w-5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 2l8 4v6c0 5-3.5 9-8 10-4.5-1-8-5-8-10V6l8-4z"/>
              </svg>
            </div>
            <div>
              <h1 className="text-base font-bold leading-tight tracking-tight text-gray-900">ProofHire Shield</h1>
              <p className="text-xs text-gray-500">Candidate intelligence — secure by design</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <SignedOut>
              <SignInButton mode="modal">
                <button className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm font-medium text-gray-700 shadow-sm transition hover:border-gray-400 hover:bg-gray-50">
                  Sign in
                </button>
              </SignInButton>
            </SignedOut>
            <SignedIn>
              <OrganizationSwitcher hidePersonal={false} />
              <span className="hidden text-xs text-gray-400 sm:inline">History enabled</span>
              <UserButton afterSignOutUrl="/" />
            </SignedIn>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-5xl px-6 py-8 space-y-8">
        <SignedIn>
          <div className="space-y-4">
            <QuotaMeter
              status={billing}
              isOrgAdmin={isOrgAdmin}
              hasActiveOrg={Boolean(orgId)}
              onUpgrade={() => setPricingOpen(true)}
              onManage={() => handleManage('user')}
              onManageOrg={() => handleManage('org')}
            />
            <HistoryView refreshKey={historyKey} onSelect={handleSelectScan} />
          </div>
        </SignedIn>

        {!result && (
          <div className="space-y-10">
            {/* Hero */}
            <div className="text-center pt-6 pb-2">
              <div
                className="inline-flex items-center gap-2 rounded-full border border-red-100 bg-red-50/80 px-4 py-1.5 text-xs font-medium text-red-700 shadow-sm animate-fade-in-up"
              >
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-red-500"></span>
                Real prompt injections detected in the wild — is your team safe?
              </div>
              <h2
                className="mb-5 mt-5 text-4xl font-bold tracking-tight text-gray-900 sm:text-5xl lg:text-6xl animate-fade-in-up"
                style={{ animationDelay: '60ms' }}
              >
                Every CV is a potential
                <br />
                <span className="bg-gradient-to-r from-blue-600 via-blue-500 to-indigo-500 bg-clip-text text-transparent">
                  security threat.
                </span>
              </h2>
              <p
                className="mx-auto mb-3 max-w-2xl text-base leading-relaxed text-gray-500 sm:text-lg animate-fade-in-up"
                style={{ animationDelay: '120ms' }}
              >
                Candidates hide invisible instructions inside CVs to manipulate AI hiring tools.
                ProofHire Shield detects them before they reach your workflow.
              </p>
              <p
                className="text-sm text-gray-400 animate-fade-in-up"
                style={{ animationDelay: '180ms' }}
              >
                No account needed · Results in seconds · Free to try
              </p>
            </div>

            {/* Feature cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div
                className="group rounded-xl border border-gray-100 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-red-100 hover:shadow-md animate-fade-in-up"
                style={{ animationDelay: '240ms' }}
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-red-50 to-red-100 ring-1 ring-red-100/50 transition group-hover:ring-red-200">
                  <svg className="h-5 w-5 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 9v2m0 4h.01M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z"/></svg>
                </div>
                <h3 className="mb-1 text-sm font-semibold text-gray-900">Threat Detection</h3>
                <p className="text-xs leading-relaxed text-gray-500">8 prompt injection patterns, PII scanning, hidden zero-width characters, base64 payloads, and PDF metadata attacks.</p>
              </div>
              <div
                className="group rounded-xl border border-gray-100 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-blue-100 hover:shadow-md animate-fade-in-up"
                style={{ animationDelay: '300ms' }}
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-blue-50 to-blue-100 ring-1 ring-blue-100/50 transition group-hover:ring-blue-200">
                  <svg className="h-5 w-5 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"/></svg>
                </div>
                <h3 className="mb-1 text-sm font-semibold text-gray-900">Candidate Intelligence</h3>
                <p className="text-xs leading-relaxed text-gray-500">Skills extraction across 9 categories, experience tier, JD match scoring, completeness meter, and red flag detection.</p>
              </div>
              <div
                className="group rounded-xl border border-gray-100 bg-white p-5 shadow-sm transition-all duration-200 hover:-translate-y-0.5 hover:border-purple-100 hover:shadow-md animate-fade-in-up"
                style={{ animationDelay: '360ms' }}
              >
                <div className="mb-3 flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-purple-50 to-purple-100 ring-1 ring-purple-100/50 transition group-hover:ring-purple-200">
                  <svg className="h-5 w-5 text-purple-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z"/></svg>
                </div>
                <h3 className="mb-1 text-sm font-semibold text-gray-900">AI Assessment</h3>
                <p className="text-xs leading-relaxed text-gray-500">LLM-powered 7-dimension candidate report with interview probes, verifiability signals, and an overall recommendation.</p>
              </div>
            </div>

            {/* Upload CTA */}
            <div
              className="animate-fade-in-up"
              style={{ animationDelay: '420ms' }}
            >
              <FileUpload onFile={handleFile} loading={loading} />
            </div>

            {/* Trust bar */}
            <div className="flex flex-wrap items-center justify-center gap-x-6 gap-y-3 border-t border-gray-200/60 pt-6 pb-4 text-xs text-gray-400">
              <span className="inline-flex items-center gap-1.5">
                <svg className="h-3.5 w-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M12 15v2m0 0v.01M5 11V7a7 7 0 1114 0v4a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2z"/></svg>
                CV text never stored without your account
              </span>
              <span className="inline-flex items-center gap-1.5">
                <svg className="h-3.5 w-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M13 10V3L4 14h7v7l9-11h-7z"/></svg>
                Zero-LLM threat detection
              </span>
              <span className="inline-flex items-center gap-1.5">
                <svg className="h-3.5 w-3.5 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z"/></svg>
                Supports PDF · DOCX · TXT
              </span>
              <span className="inline-flex items-center gap-1.5">
                <svg className="h-3.5 w-3.5 text-green-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7"/></svg>
                385+ security tests
              </span>
            </div>
          </div>
        )}

        {result && <FileUpload onFile={handleFile} loading={loading} />}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700">
            {error}
          </div>
        )}

        {result && (
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
            {activeTab === 'assessment' && (
              <AssessmentTab
                result={result}
                billing={billing}
                onUpgrade={() => setPricingOpen(true)}
              />
            )}

            <div className="mt-8">
              <JDMatcher cvText={result.safe_copy_text} />
            </div>
          </div>
        )}
      </main>

      <PricingModal
        open={pricingOpen}
        onClose={() => {
          setPricingOpen(false)
          setCheckoutError(null)
        }}
        onUpgrade={() => handleCheckout('user')}
        onUpgradeOrg={() => handleCheckout('org')}
        isOrgAdmin={isOrgAdmin}
        hasActiveOrg={Boolean(orgId)}
        busy={checkoutBusy}
        error={checkoutError}
      />
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
