interface Props {
  open: boolean
  onClose: () => void
  onUpgrade: () => void
  // Phase 8.7 — org-Pro upgrade. Admins see the firm CTA next to the personal
  // one; viewers in an org see an explanatory note instead of the firm CTA.
  onUpgradeOrg?: () => void
  isOrgAdmin?: boolean
  hasActiveOrg?: boolean
  busy: boolean
  error: string | null
}

const FREE_FEATURES = [
  '10 candidate scans per month',
  'Hidden-instruction blocking',
  'Personal-data flagging',
  'AI-writing likelihood signal',
  'Job-description matching',
  'Saved scan history',
]

const PRO_FEATURES = [
  'Everything in Free',
  'Unlimited candidate scans',
  'AI assessment reports',
]

const ORG_PRO_FEATURES = [
  'Everything in Pro for the whole firm',
  'Every member of your Clerk org unlocks Pro',
  'Single billing relationship — admin pays once',
]

function Check() {
  return <span className="mt-0.5 shrink-0 text-green-600">{'✓'}</span>
}

// The "pricing page": a Free vs Pro comparison shown in a modal. The actual
// price is presented and confirmed on Stripe's secure checkout page, so it is
// never hard-coded here (and can never drift from the configured Stripe price).
export function PricingModal({
  open,
  onClose,
  onUpgrade,
  onUpgradeOrg,
  isOrgAdmin = false,
  hasActiveOrg = false,
  busy,
  error,
}: Props) {
  if (!open) return null

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-2xl rounded-xl bg-white p-6 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-5 flex items-start justify-between">
          <div>
            <h2 className="text-lg font-bold text-gray-900">Upgrade to Pro</h2>
            <p className="text-sm text-gray-500">
              Unlimited scans and AI assessment reports.
            </p>
          </div>
          <button
            onClick={onClose}
            aria-label="Close"
            className="rounded-lg p-1 text-gray-400 hover:bg-gray-100 hover:text-gray-600"
          >
            {'✕'}
          </button>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-xl border border-gray-200 bg-white p-5">
            <p className="text-sm font-semibold text-gray-700">Free</p>
            <p className="mb-3 text-xs text-gray-400">Your current plan</p>
            <ul className="space-y-2">
              {FREE_FEATURES.map((f) => (
                <li key={f} className="flex gap-2 text-sm text-gray-600">
                  <Check />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>

          <div className="relative rounded-xl border-2 border-blue-500 bg-gradient-to-br from-blue-50 via-white to-indigo-50 p-5 shadow-md">
            <span className="absolute -top-3 left-5 inline-flex items-center gap-1 rounded-full bg-gradient-to-r from-blue-600 to-indigo-600 px-2.5 py-0.5 text-[10px] font-bold uppercase tracking-wider text-white shadow-sm">
              <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 20 20"><path d="M9.049 2.927c.3-.921 1.603-.921 1.902 0l1.07 3.292a1 1 0 00.95.69h3.462c.969 0 1.371 1.24.588 1.81l-2.8 2.034a1 1 0 00-.364 1.118l1.07 3.292c.3.921-.755 1.688-1.539 1.118l-2.8-2.034a1 1 0 00-1.175 0l-2.8 2.034c-.784.57-1.838-.197-1.539-1.118l1.07-3.292a1 1 0 00-.364-1.118L2.98 8.72c-.783-.57-.38-1.81.588-1.81h3.461a1 1 0 00.951-.69l1.07-3.292z"/></svg>
              Most popular
            </span>
            <p className="text-sm font-semibold text-blue-800">Pro</p>
            <p className="mb-3 text-xs text-blue-600">Billed monthly via Stripe · cancel anytime</p>
            <ul className="space-y-2">
              {PRO_FEATURES.map((f) => (
                <li key={f} className="flex gap-2 text-sm text-blue-900">
                  <Check />
                  <span className="font-medium">{f}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <button
          onClick={onUpgrade}
          disabled={busy}
          className="mt-5 inline-flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-blue-600 to-indigo-600 px-4 py-3 text-sm font-semibold text-white shadow-md transition hover:from-blue-700 hover:to-indigo-700 hover:shadow-lg disabled:cursor-not-allowed disabled:from-gray-400 disabled:to-gray-500 disabled:shadow-none"
        >
          {busy ? (
            <>
              <svg className="h-4 w-4 animate-spin" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z" />
              </svg>
              Redirecting to checkout…
            </>
          ) : (
            <>
              Upgrade me to Pro
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6"/></svg>
            </>
          )}
        </button>

        {hasActiveOrg && (
          <div className="mt-4 rounded-lg border border-purple-200 bg-purple-50 p-4">
            <p className="text-sm font-semibold text-purple-900">
              Upgrading the whole firm
            </p>
            <ul className="mt-2 space-y-1.5">
              {ORG_PRO_FEATURES.map((f) => (
                <li key={f} className="flex gap-2 text-xs text-purple-900">
                  <Check />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
            {isOrgAdmin && onUpgradeOrg ? (
              <button
                onClick={onUpgradeOrg}
                disabled={busy}
                className="mt-3 w-full rounded-lg border border-purple-400 bg-white px-4 py-2 text-sm font-semibold text-purple-800 hover:bg-purple-100 disabled:cursor-not-allowed disabled:opacity-50"
              >
                Upgrade firm to Pro
              </button>
            ) : (
              <p className="mt-3 text-xs italic text-purple-700">
                Only an org admin can purchase a firm subscription. Ask your
                admin to upgrade so every member unlocks Pro.
              </p>
            )}
          </div>
        )}

        <p className="mt-3 text-center text-xs text-gray-400">
          You will see the price and confirm securely on the next step.
        </p>
        {error && <p className="mt-3 text-center text-sm text-red-600">{error}</p>}
      </div>
    </div>
  )
}
