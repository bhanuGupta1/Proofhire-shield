import { useEffect, useState } from 'react'

const KEY = 'proofhire_consent_ack'

// A lightweight, dismissible privacy notice. Persisted per browser so it shows
// once. Not a cookie wall — ProofHire stores CV data only for signed-in users
// and never the raw PII, which the banner states.
export function ConsentBanner() {
  const [show, setShow] = useState(false)

  useEffect(() => {
    try {
      setShow(window.localStorage.getItem(KEY) !== '1')
    } catch {
      setShow(true)
    }
  }, [])

  function dismiss() {
    try {
      window.localStorage.setItem(KEY, '1')
    } catch {
      // Ignore private-mode failures.
    }
    setShow(false)
  }

  if (!show) return null

  return (
    <div className="fixed inset-x-0 bottom-0 z-[90] border-t border-gray-200 bg-white/95 px-4 py-3 shadow-lg backdrop-blur">
      <div className="mx-auto flex max-w-5xl flex-col items-start justify-between gap-2 sm:flex-row sm:items-center">
        <p className="text-xs leading-relaxed text-gray-500">
          ProofHire Shield scans CVs for hidden instructions and personal data.
          Raw CV text is never stored — signed-in accounts keep only a scrubbed
          safe copy. By continuing you acknowledge this processing.
        </p>
        <button
          onClick={dismiss}
          className="shrink-0 rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-gray-700"
        >
          Got it
        </button>
      </div>
    </div>
  )
}
