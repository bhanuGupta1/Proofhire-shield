import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

interface Command {
  label: string
  hint: string
  to: string
}

const COMMANDS: Command[] = [
  { label: 'Dashboard', hint: 'Overview & Today', to: '/dashboard' },
  { label: 'New Scan', hint: 'Scan a CV', to: '/' },
  { label: 'Candidates', hint: 'Your talent pool', to: '/candidates' },
  { label: 'Jobs', hint: 'Open roles', to: '/jobs' },
  { label: 'New Job', hint: 'Create a role', to: '/jobs/new' },
  { label: 'Clients', hint: 'Companies', to: '/clients' },
  { label: 'Talent Search', hint: 'Search candidates', to: '/talent' },
  { label: 'Audit Log', hint: 'Activity trail', to: '/audit' },
]

// Global command palette — ⌘K / Ctrl-K opens a fuzzy navigation switcher.
export function CommandPalette() {
  const navigate = useNavigate()
  const [open, setOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [active, setActive] = useState(0)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setOpen((o) => !o)
        setQuery('')
        setActive(0)
      } else if (e.key === 'Escape') {
        setOpen(false)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  const results = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return COMMANDS
    return COMMANDS.filter(
      (c) =>
        c.label.toLowerCase().includes(q) || c.hint.toLowerCase().includes(q),
    )
  }, [query])

  if (!open) return null

  function go(to: string) {
    setOpen(false)
    navigate(to)
  }

  return (
    <div
      className="fixed inset-0 z-[100] flex items-start justify-center bg-black/30 pt-[15vh] backdrop-blur-sm"
      onClick={() => setOpen(false)}
    >
      <div
        className="w-full max-w-lg overflow-hidden rounded-xl border border-gray-200 bg-white shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <input
          autoFocus
          value={query}
          onChange={(e) => {
            setQuery(e.target.value)
            setActive(0)
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowDown') {
              e.preventDefault()
              setActive((a) => Math.min(a + 1, results.length - 1))
            } else if (e.key === 'ArrowUp') {
              e.preventDefault()
              setActive((a) => Math.max(a - 1, 0))
            } else if (e.key === 'Enter' && results[active]) {
              go(results[active].to)
            }
          }}
          placeholder="Jump to…"
          className="w-full border-b border-gray-100 px-4 py-3 text-sm outline-none"
        />
        <ul className="max-h-80 overflow-y-auto py-1">
          {results.length === 0 ? (
            <li className="px-4 py-6 text-center text-xs text-gray-400">No matches</li>
          ) : (
            results.map((c, i) => (
              <li key={c.to}>
                <button
                  onMouseEnter={() => setActive(i)}
                  onClick={() => go(c.to)}
                  className={`flex w-full items-center justify-between px-4 py-2.5 text-left text-sm ${
                    i === active ? 'bg-blue-50 text-blue-700' : 'text-gray-700'
                  }`}
                >
                  <span className="font-medium">{c.label}</span>
                  <span className="text-xs text-gray-400">{c.hint}</span>
                </button>
              </li>
            ))
          )}
        </ul>
        <div className="border-t border-gray-100 px-4 py-2 text-[11px] text-gray-400">
          ↑↓ to navigate · ↵ to open · esc to close
        </div>
      </div>
    </div>
  )
}
