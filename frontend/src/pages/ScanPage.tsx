import { useState, useEffect } from 'react'
import { useAuth, SignedIn } from '@clerk/clerk-react'
import { useNavigate } from 'react-router-dom'
import { FileUpload } from '../components/FileUpload'
import { HistoryView } from '../components/HistoryView'
import { RiskTab } from '../components/tabs/RiskTab'
import { MatchTab } from '../components/tabs/MatchTab'
import { ProofTab } from '../components/tabs/ProofTab'
import { AssessmentTab } from '../components/tabs/AssessmentTab'
import { JDMatcher } from '../components/JDMatcher'
import { QuotaMeter } from '../components/QuotaMeter'
import { PricingModal } from '../components/PricingModal'
import {
  OnboardingTour,
  TourLauncherButton,
  useOnboardingTour,
} from '../components/OnboardingTour'
import {
  scanCV,
  getScan,
  getBillingStatus,
  startCheckout,
  openBillingPortal,
  createCandidate,
} from '../lib/api'
import type { ScanResult, BillingStatus, MatchEngine } from '../lib/types'

const MATCH_ENGINE_KEY = 'proofhire_match_engine'

function loadInitialMatchEngine(): MatchEngine {
  if (typeof window === 'undefined') return 'llm'
  const v = window.localStorage.getItem(MATCH_ENGINE_KEY)
  return v === 'regex' ? 'regex' : 'llm'
}

type Tab = 'risk' | 'match' | 'proof' | 'assessment'

const TABS: { id: Tab; label: string }[] = [
  { id: 'risk', label: 'Risk' },
  { id: 'match', label: 'Match' },
  { id: 'proof', label: 'Proof' },
  { id: 'assessment', label: 'Assessment' },
]

export function ScanPage() {
  const { getToken, isSignedIn, orgId, orgRole } = useAuth()
  const navigate = useNavigate()
  const isOrgAdmin =
    Boolean(orgId) && (orgRole === 'org:admin' || orgRole === 'admin')

  const [result, setResult] = useState<ScanResult | null>(null)
  const [file, setFile] = useState<File | null>(null)
  const [matchEngine, setMatchEngineState] = useState<MatchEngine>(
    () => loadInitialMatchEngine(),
  )
  function setMatchEngine(next: MatchEngine) {
    setMatchEngineState(next)
    try {
      window.localStorage.setItem(MATCH_ENGINE_KEY, next)
    } catch {
      // Private-mode / quota — ignore; choice still applies this session.
    }
  }
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<Tab>('risk')
  const [historyKey, setHistoryKey] = useState(0)
  const [billing, setBilling] = useState<BillingStatus | null>(null)
  const [pricingOpen, setPricingOpen] = useState(false)
  const [checkoutBusy, setCheckoutBusy] = useState(false)
  const [checkoutError, setCheckoutError] = useState<string | null>(null)
  // Save-as-candidate state for the current result.
  const [savingCandidate, setSavingCandidate] = useState(false)
  const tour = useOnboardingTour()

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
      const resp = await scanCV(f, token, matchEngine)
      if (!resp.ok || !resp.result) {
        setError(resp.error ?? 'Scan failed')
      } else {
        setResult(resp.result)
        setActiveTab('risk')
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

  // Promote the current scan into a durable candidate record, then jump to the
  // candidate's profile. Only available when the scan was persisted (scan_id).
  async function handleSaveCandidate() {
    if (!result?.scan_id) return
    setSavingCandidate(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to save candidates.')
        return
      }
      const candidate = await createCandidate({ scan_id: result.scan_id }, token)
      navigate(`/candidates/${candidate.id}`)
    } catch (e) {
      setError((e as Error).message || 'Could not save candidate.')
    } finally {
      setSavingCandidate(false)
    }
  }

  return (
    <div className="space-y-8">
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
        <div className="space-y-8">
          <div className="text-center pt-2">
            <h2 className="mb-3 text-3xl font-bold tracking-tight text-gray-900 sm:text-4xl">
              Every CV is a potential{' '}
              <span className="bg-gradient-to-r from-blue-600 via-blue-500 to-indigo-500 bg-clip-text text-transparent">
                security threat.
              </span>
            </h2>
            <p className="mx-auto mb-2 max-w-2xl text-base leading-relaxed text-gray-500">
              Candidates hide invisible instructions inside CVs to manipulate AI
              hiring tools. ProofHire Shield detects them before they reach your
              workflow — then turns the CV into a candidate you can pipeline.
            </p>
            <p className="text-sm text-gray-400">
              No account needed · Results in seconds · Free to try
            </p>
          </div>

          <div data-tour="upload">
            <FileUpload onFile={handleFile} loading={loading} />
            <div className="mx-auto mt-4 flex max-w-md items-center justify-between rounded-lg border border-gray-200 bg-white/70 px-4 py-2.5 text-xs shadow-sm backdrop-blur-sm">
              <div>
                <p className="font-medium text-gray-700">Match engine</p>
                <p className="mt-0.5 text-[11px] leading-tight text-gray-400">
                  {matchEngine === 'llm'
                    ? 'AI-assisted reads the CV with context.'
                    : 'Fast regex — deterministic, but can miss context in rare cases.'}
                </p>
              </div>
              <div className="flex shrink-0 rounded-md border border-gray-200 bg-gray-50 p-0.5">
                <button
                  type="button"
                  onClick={() => setMatchEngine('llm')}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                    matchEngine === 'llm'
                      ? 'bg-white text-blue-700 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  AI
                </button>
                <button
                  type="button"
                  onClick={() => setMatchEngine('regex')}
                  className={`rounded px-2.5 py-1 text-[11px] font-semibold transition ${
                    matchEngine === 'regex'
                      ? 'bg-white text-blue-700 shadow-sm'
                      : 'text-gray-500 hover:text-gray-700'
                  }`}
                >
                  Fast
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {result && <FileUpload onFile={handleFile} loading={loading} />}

      {error && (
        <div className="flex items-start gap-3 rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700 shadow-sm">
          <svg className="mt-0.5 h-4 w-4 shrink-0 text-red-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
          <span className="grow">{error}</span>
          <button
            onClick={() => setError(null)}
            aria-label="Dismiss error"
            className="shrink-0 rounded-md p-1 text-red-400 transition hover:bg-red-100 hover:text-red-600"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
          </button>
        </div>
      )}

      {result && (
        <div>
          <div className="mb-5 flex items-center justify-between gap-3 rounded-xl border border-gray-200 bg-white px-4 py-3 shadow-sm">
            <div className="flex min-w-0 items-center gap-3">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-gray-50 to-gray-100 ring-1 ring-gray-100">
                <svg className="h-4 w-4 text-gray-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.8} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414A1 1 0 0119 9.414V19a2 2 0 01-2 2z" /></svg>
              </div>
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-gray-900">{result.filename}</p>
                <p className="text-xs text-gray-500">Scan complete · {result.risk_score}/100 risk score</p>
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              {/* Save-as-candidate: only when the scan was persisted. */}
              {result.scan_id && (
                <button
                  onClick={handleSaveCandidate}
                  disabled={savingCandidate}
                  className="rounded-lg border border-blue-200 bg-blue-50 px-3 py-1.5 text-xs font-semibold text-blue-700 shadow-sm transition hover:bg-blue-100 disabled:opacity-60"
                >
                  {savingCandidate ? 'Saving…' : 'Save as candidate'}
                </button>
              )}
              <span className={`rounded-full px-2.5 py-1 text-xs font-bold tracking-wider
                ${result.risk_level === 'GREEN' ? 'bg-green-100 text-green-700' : ''}
                ${result.risk_level === 'ORANGE' ? 'bg-amber-100 text-amber-700' : ''}
                ${result.risk_level === 'RED' ? 'bg-red-100 text-red-700' : ''}`}
              >
                {result.risk_level}
              </span>
            </div>
          </div>

          <div className="mb-5 inline-flex gap-1 rounded-xl border border-gray-200 bg-white/80 p-1 shadow-sm backdrop-blur-sm">
            {TABS.map((t) => (
              <button
                key={t.id}
                data-tour={t.id === 'risk' || t.id === 'match' ? t.id : undefined}
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

          <div className="mt-8" data-tour="jd">
            <JDMatcher cvText={result.safe_copy_text} />
          </div>
        </div>
      )}

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

      <TourLauncherButton onClick={tour.show} />
      <OnboardingTour open={tour.open} onClose={tour.close} />
    </div>
  )
}
