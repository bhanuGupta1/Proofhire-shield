export function MatchTab() {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <div className="mb-4 rounded-full bg-blue-50 p-4">
        <svg className="h-8 w-8 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
        </svg>
      </div>
      <h2 className="text-lg font-semibold text-gray-800">Match scoring — Phase 2</h2>
      <p className="mt-2 max-w-sm text-sm text-gray-500">
        Match scoring coming in Phase 2 — skill fit, experience tier, and interview probes
        in recruiter language.
      </p>
    </div>
  )
}
