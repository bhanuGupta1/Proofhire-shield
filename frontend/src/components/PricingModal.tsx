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
          <div className="rounded-xl border border-gray-200 p-5">
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

          <div className="rounded-xl border-2 border-blue-500 bg-blue-50 p-5">
            <p className="text-sm font-semibold text-blue-800">Pro</p>
            <p className="mb-3 text-xs text-blue-600">Billed monthly via Stripe</p>
            <ul className="space-y-2">
              {PRO_FEATURES.map((f) => (
                <li key={f} className="flex gap-2 text-sm text-blue-900">
                  <Check />
                  <span>{f}</span>
                </li>
              ))}
            </ul>
          </div>
        </div>

        <button
          onClick={onUpgrade}
          disabled={busy}
          className="mt-5 w-full rounded-lg bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? 'Redirecting to checkout…' : 'Upgrade me to Pro'}
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
