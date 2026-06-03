import type { BillingStatus } from '../lib/types'

interface Props {
  status: BillingStatus | null
  // Phase 8.7 — Clerk org context for the "Upgrade Firm" / "Manage org billing"
  // entry points. Non-admins see read-only "managed by admin" copy.
  isOrgAdmin?: boolean
  hasActiveOrg?: boolean
  onUpgrade: () => void
  onManage: () => void
  onManageOrg?: () => void
}

function renewsLabel(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return ` · renews ${d.toLocaleDateString()}`
}

// Compact plan + usage strip shown to signed-in users. Renders nothing when we
// have no billing status (anonymous, or a deployment without a database) so the
// meter never blocks the core scan flow.
export function QuotaMeter({
  status,
  isOrgAdmin = false,
  hasActiveOrg = false,
  onUpgrade,
  onManage,
  onManageOrg,
}: Props) {
  if (!status) return null

  if (status.is_pro) {
    const viaOrg = status.via_org === true
    return (
      <div className="flex items-center justify-between rounded-lg border border-blue-200 bg-blue-50 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded-full bg-blue-600 px-2 py-0.5 text-xs font-bold tracking-wide text-white">
            PRO
          </span>
          <span className="text-sm font-medium text-blue-900">
            {viaOrg ? 'Unlimited scans · via your firm' : `Unlimited scans${renewsLabel(status.current_period_end)}`}
          </span>
        </div>
        {viaOrg ? (
          isOrgAdmin && onManageOrg ? (
            <button
              onClick={onManageOrg}
              className="rounded-lg border border-blue-300 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100"
            >
              Manage firm billing
            </button>
          ) : (
            <span className="text-xs italic text-blue-700">
              Billing managed by admin
            </span>
          )
        ) : (
          <button
            onClick={onManage}
            className="rounded-lg border border-blue-300 px-3 py-1.5 text-sm font-medium text-blue-700 hover:bg-blue-100"
          >
            Manage billing
          </button>
        )}
      </div>
    )
  }

  const used = status.scans_used
  const limit = status.scan_limit
  const pct = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0
  const atLimit = used >= limit

  return (
    <div className="rounded-lg border border-gray-200 bg-white px-4 py-3">
      <div className="flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-gray-700">Free plan</span>
        <button
          onClick={onUpgrade}
          className="rounded-lg bg-blue-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-blue-700"
        >
          Upgrade to Pro
        </button>
      </div>
      <div className="mt-2 h-2 w-full overflow-hidden rounded-full bg-gray-100">
        <div
          className={`h-full rounded-full ${atLimit ? 'bg-red-500' : 'bg-blue-600'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="mt-1.5 text-xs text-gray-500">
        {used} / {limit} scans this month{atLimit ? ' · limit reached' : ''}
      </p>
      {hasActiveOrg && !isOrgAdmin && (
        <p className="mt-1.5 text-xs italic text-gray-400">
          Or ask your firm admin to upgrade the whole organisation.
        </p>
      )}
    </div>
  )
}
