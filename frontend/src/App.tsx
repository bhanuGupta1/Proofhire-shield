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
              <OrganizationSwitcher hidePersonal={false} />
              <span className="text-xs text-gray-400">History enabled</span>
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

        <FileUpload onFile={handleFile} loading={loading} />

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
