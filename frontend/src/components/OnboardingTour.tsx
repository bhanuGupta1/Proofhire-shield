import { useEffect, useLayoutEffect, useState } from 'react'

/**
 * First-visit walkthrough. Zero deps — pure React + Tailwind.
 *
 * Each step targets a DOM element via a `data-tour="..."` attribute. The
 * tour reads the element's bounding box, draws a soft glow ring around
 * it, and floats a tooltip card with title + body next to it. If the
 * target element isn't on screen yet (steps 2-4 require a scan), the
 * tooltip centres itself and still explains what's coming.
 *
 * Visibility:
 * - On first visit (no `proofhire_tour_seen` in localStorage) the tour
 *   auto-opens.
 * - A persistent "?" button in the bottom-right corner re-opens it any
 *   time. The localStorage flag is set on first dismiss; reopening from
 *   the "?" button does NOT clear it.
 */

const STORAGE_KEY = 'proofhire_tour_seen'

const STEPS: ReadonlyArray<{
  target: string
  title: string
  body: string
}> = [
  {
    target: 'upload',
    title: 'Drop any CV here',
    body: 'PDF, DOCX, or TXT. We scan it instantly for hidden instructions, personal-data leaks, and AI-generated text — and extract candidate intelligence in the same pass.',
  },
  {
    target: 'risk',
    title: 'Risk tab',
    body: 'Detects prompt-injection attacks, PII leaks, and AI-generated content hidden in the CV. Every finding is shown with the matched text so you can verify it yourself.',
  },
  {
    target: 'match',
    title: 'Match tab',
    body: 'Extracts skills across 9 categories, classifies experience tier, and writes interview probes — all without a job description. Great for first-pass triage.',
  },
  {
    target: 'jd',
    title: 'JD Matcher',
    body: 'Paste a job description to get a match score showing which skills align and which are missing. The score is capped when the JD is too sparse to be reliable.',
  },
]

const TOTAL = STEPS.length

interface Rect {
  top: number
  left: number
  width: number
  height: number
}

function getRect(target: string): Rect | null {
  if (typeof document === 'undefined') return null
  const el = document.querySelector(`[data-tour="${target}"]`) as HTMLElement | null
  if (!el) return null
  const r = el.getBoundingClientRect()
  if (r.width === 0 && r.height === 0) return null
  return { top: r.top, left: r.left, width: r.width, height: r.height }
}

function tooltipPosition(rect: Rect | null): { top: number; left: number } {
  if (typeof window === 'undefined') return { top: 100, left: 100 }
  const W = window.innerWidth
  const H = window.innerHeight
  const TOOLTIP_W = 320
  const TOOLTIP_H = 200
  if (!rect) {
    // Fallback to centre when the target isn't on screen yet.
    return { top: Math.max(16, H / 2 - TOOLTIP_H / 2), left: Math.max(16, W / 2 - TOOLTIP_W / 2) }
  }
  // Prefer below the target; otherwise above; otherwise to the right.
  const spaceBelow = H - (rect.top + rect.height)
  const spaceAbove = rect.top
  let top: number
  if (spaceBelow >= TOOLTIP_H + 24) {
    top = rect.top + rect.height + 16
  } else if (spaceAbove >= TOOLTIP_H + 24) {
    top = rect.top - TOOLTIP_H - 16
  } else {
    top = Math.max(16, H / 2 - TOOLTIP_H / 2)
  }
  let left = rect.left + rect.width / 2 - TOOLTIP_W / 2
  left = Math.max(16, Math.min(left, W - TOOLTIP_W - 16))
  return { top, left }
}


interface Props {
  open: boolean
  onClose: () => void
}

export function OnboardingTour({ open, onClose }: Props) {
  const [step, setStep] = useState(0)
  const [rect, setRect] = useState<Rect | null>(null)

  // Recompute the target rect after layout each time the step changes OR
  // the window resizes — the target may not exist yet on the first paint
  // (e.g. tabs only render after a scan).
  useLayoutEffect(() => {
    if (!open) return
    function update() {
      setRect(getRect(STEPS[step].target))
    }
    update()
    // Poll briefly so a late-rendered target (e.g. result tab after scan)
    // still gets a ring. Stops after the rect lands once.
    let tries = 0
    const id = window.setInterval(() => {
      const r = getRect(STEPS[step].target)
      if (r || tries > 5) {
        setRect(r)
        window.clearInterval(id)
      }
      tries++
    }, 200)
    window.addEventListener('resize', update)
    window.addEventListener('scroll', update, true)
    return () => {
      window.clearInterval(id)
      window.removeEventListener('resize', update)
      window.removeEventListener('scroll', update, true)
    }
  }, [step, open])

  // Reset to step 0 every time the tour is opened.
  useEffect(() => {
    if (open) setStep(0)
  }, [open])

  // Escape key dismisses the tour.
  useEffect(() => {
    if (!open) return
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
      if (e.key === 'ArrowRight') setStep((s) => Math.min(TOTAL - 1, s + 1))
      if (e.key === 'ArrowLeft') setStep((s) => Math.max(0, s - 1))
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  const pos = tooltipPosition(rect)
  const current = STEPS[step]
  const isLast = step === TOTAL - 1

  return (
    <div className="fixed inset-0 z-50">
      {/* Backdrop. Pointer events on the backdrop dismiss the tour
          when the user clicks outside the tooltip. */}
      <div
        className="absolute inset-0 bg-slate-900/40 backdrop-blur-[1px]"
        onClick={onClose}
        aria-hidden
      />

      {/* Glow ring around the target. Pointer-events none so it doesn't
          intercept clicks on the underlying element. */}
      {rect && (
        <div
          className="pointer-events-none absolute rounded-xl ring-4 ring-blue-400/70 ring-offset-2 ring-offset-white/10 transition-all duration-300"
          style={{
            top: rect.top - 4,
            left: rect.left - 4,
            width: rect.width + 8,
            height: rect.height + 8,
            boxShadow: '0 0 0 9999px rgba(15, 23, 42, 0.35)',
          }}
        />
      )}

      {/* Tooltip card. */}
      <div
        className="absolute w-[320px] rounded-xl border border-gray-200 bg-white p-5 shadow-2xl animate-fade-in-up"
        style={{ top: pos.top, left: pos.left }}
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-labelledby="tour-title"
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="text-[10px] font-bold uppercase tracking-wider text-gray-400">
            Step {step + 1} of {TOTAL}
          </span>
          <button
            onClick={onClose}
            aria-label="Skip tour"
            className="rounded p-1 text-gray-400 transition hover:bg-gray-100 hover:text-gray-700"
          >
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>
        <h3 id="tour-title" className="mb-1 text-base font-bold text-gray-900">
          {current.title}
        </h3>
        <p className="mb-4 text-sm leading-relaxed text-gray-600">{current.body}</p>

        {/* Progress dots */}
        <div className="mb-4 flex gap-1.5">
          {STEPS.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-full transition ${
                i === step ? 'bg-blue-600' : i < step ? 'bg-blue-300' : 'bg-gray-200'
              }`}
            />
          ))}
        </div>

        <div className="flex items-center justify-between gap-2">
          <button
            onClick={onClose}
            className="text-xs text-gray-400 transition hover:text-gray-600 hover:underline"
          >
            Skip tour
          </button>
          <div className="flex gap-2">
            <button
              onClick={() => setStep((s) => Math.max(0, s - 1))}
              disabled={step === 0}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-xs font-medium text-gray-700 transition hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Previous
            </button>
            <button
              onClick={() => {
                if (isLast) onClose()
                else setStep((s) => s + 1)
              }}
              className="inline-flex items-center gap-1 rounded-md bg-gradient-to-r from-blue-600 to-indigo-600 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:from-blue-700 hover:to-indigo-700"
            >
              {isLast ? 'Got it' : 'Next'}
              {!isLast && (
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}


/**
 * Persistent "?" pill in the bottom-right that re-opens the tour. Renders
 * regardless of sign-in state so a returning visitor can always replay it.
 */
export function TourLauncherButton({ onClick }: { onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      aria-label="Open product tour"
      className="fixed bottom-4 right-4 z-30 flex h-11 w-11 items-center justify-center rounded-full bg-gradient-to-br from-blue-600 to-indigo-600 text-white shadow-lg shadow-blue-500/30 transition hover:scale-105 hover:shadow-xl"
    >
      <span className="text-lg font-bold leading-none">?</span>
    </button>
  )
}


/**
 * Hook helper for App.tsx. Wraps the localStorage check + state so the
 * call site stays small.
 */
export function useOnboardingTour(): {
  open: boolean
  show: () => void
  close: () => void
} {
  const [open, setOpen] = useState<boolean>(() => {
    if (typeof window === 'undefined') return false
    return window.localStorage.getItem(STORAGE_KEY) !== '1'
  })
  return {
    open,
    show: () => setOpen(true),
    close: () => {
      setOpen(false)
      try {
        window.localStorage.setItem(STORAGE_KEY, '1')
      } catch {
        // privacy-mode / quota — silently ignore. The tour just shows again
        // next visit, which is the correct degraded behaviour.
      }
    },
  }
}
