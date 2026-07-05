import { useEffect, useState } from 'react'
import { useAuth } from '@clerk/clerk-react'
import { Link } from 'react-router-dom'
import {
  addPlacement,
  addStage,
  deleteStage,
  getPipeline,
  listCandidates,
  movePlacement,
  removePlacement,
} from '../lib/api'
import type { Candidate, PipelineBoard as Board } from '../lib/types'

function riskClasses(level: string | null): string {
  if (level === 'GREEN') return 'bg-green-100 text-green-700'
  if (level === 'ORANGE') return 'bg-amber-100 text-amber-700'
  if (level === 'RED') return 'bg-red-100 text-red-700'
  return 'bg-gray-100 text-gray-400'
}

export function PipelineBoard({ jobId }: { jobId: string }) {
  const { getToken } = useAuth()
  const [board, setBoard] = useState<Board | null>(null)
  const [candidates, setCandidates] = useState<Candidate[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [dragId, setDragId] = useState<string | null>(null)
  const [pickCandidate, setPickCandidate] = useState('')
  const [newStage, setNewStage] = useState('')
  const [busy, setBusy] = useState(false)

  async function refresh() {
    try {
      const token = await getToken()
      if (!token) {
        setError('Sign in to view the pipeline.')
        return
      }
      const [b, cs] = await Promise.all([
        getPipeline(jobId, token),
        listCandidates(token),
      ])
      setBoard(b)
      setCandidates(cs.candidates)
    } catch (e) {
      setError((e as Error).message || 'Could not load pipeline.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId])

  // Candidate ids already somewhere on the board — excluded from the picker.
  const placedIds = new Set(
    board?.stages.flatMap((s) => s.candidates.map((c) => c.candidate_id)) ?? [],
  )
  const available = candidates.filter((c) => !placedIds.has(c.id))

  async function withToken(fn: (token: string) => Promise<unknown>) {
    setBusy(true)
    setError(null)
    try {
      const token = await getToken()
      if (!token) return
      await fn(token)
      await refresh()
    } catch (e) {
      setError((e as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function handleDrop(stageId: string) {
    if (!dragId) return
    const id = dragId
    setDragId(null)
    await withToken((token) => movePlacement(id, stageId, token))
  }

  if (loading) {
    return <div className="py-10 text-center text-sm text-gray-400">Loading pipeline…</div>
  }
  if (error && !board) {
    return (
      <div className="rounded-lg border border-red-200 bg-red-50/80 px-4 py-3 text-sm text-red-700">
        {error}
      </div>
    )
  }
  if (!board) return null

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500">
          Pipeline
        </h3>
        <div className="flex items-center gap-2">
          {available.length > 0 ? (
            <>
              <select
                value={pickCandidate}
                onChange={(e) => setPickCandidate(e.target.value)}
                className="rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-blue-400 focus:outline-none"
              >
                <option value="">Add candidate…</option>
                {available.map((c) => (
                  <option key={c.id} value={c.id}>
                    {c.full_name}
                  </option>
                ))}
              </select>
              <button
                disabled={!pickCandidate || busy}
                onClick={() =>
                  void withToken((token) =>
                    addPlacement(jobId, pickCandidate, token),
                  ).then(() => setPickCandidate(''))
                }
                className="rounded-lg bg-gray-900 px-3 py-1.5 text-xs font-semibold text-white shadow-sm transition hover:bg-gray-700 disabled:opacity-50"
              >
                Add
              </button>
            </>
          ) : (
            <span className="text-xs text-gray-400">
              {candidates.length === 0 ? (
                <Link to="/candidates" className="text-blue-600 hover:underline">
                  Save a candidate first
                </Link>
              ) : (
                'All candidates are on the board'
              )}
            </span>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-lg border border-red-200 bg-red-50/80 px-3 py-2 text-xs text-red-700">
          {error}
        </div>
      )}

      <div className="flex gap-3 overflow-x-auto pb-2">
        {board.stages.map((stage) => (
          <div
            key={stage.id}
            onDragOver={(e) => e.preventDefault()}
            onDrop={() => void handleDrop(stage.id)}
            className="flex w-60 shrink-0 flex-col rounded-xl border border-gray-200 bg-gray-50/70 p-2"
          >
            <div className="mb-2 flex items-center justify-between px-1">
              <div className="flex items-center gap-1.5">
                <span className="text-xs font-semibold text-gray-700">{stage.name}</span>
                <span className="rounded-full bg-gray-200 px-1.5 text-[10px] font-semibold text-gray-500">
                  {stage.candidates.length}
                </span>
              </div>
              {board.stages.length > 1 && (
                <button
                  title="Delete stage"
                  onClick={() => void withToken((token) => deleteStage(stage.id, token))}
                  className="text-gray-300 transition hover:text-red-500"
                >
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                </button>
              )}
            </div>

            <div className="space-y-2">
              {stage.candidates.map((c) => (
                <div
                  key={c.placement_id}
                  draggable
                  onDragStart={() => setDragId(c.placement_id)}
                  onDragEnd={() => setDragId(null)}
                  className="group cursor-grab rounded-lg border border-gray-200 bg-white p-2.5 shadow-sm transition hover:shadow active:cursor-grabbing"
                >
                  <div className="flex items-start justify-between gap-2">
                    <Link
                      to={`/candidates/${c.candidate_id}`}
                      className="text-xs font-semibold text-gray-900 hover:text-blue-700"
                    >
                      {c.full_name}
                    </Link>
                    <button
                      title="Remove from pipeline"
                      onClick={() =>
                        void withToken((token) => removePlacement(c.placement_id, token))
                      }
                      className="shrink-0 text-gray-300 opacity-0 transition group-hover:opacity-100 hover:text-red-500"
                    >
                      <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                    </button>
                  </div>
                  {c.headline && (
                    <p className="mt-0.5 truncate text-[11px] text-gray-400">{c.headline}</p>
                  )}
                  {c.risk_level && (
                    <span className={`mt-1.5 inline-block rounded-full px-1.5 py-0.5 text-[10px] font-bold tracking-wide ${riskClasses(c.risk_level)}`}>
                      {c.risk_level}
                    </span>
                  )}
                </div>
              ))}
              {stage.candidates.length === 0 && (
                <div className="rounded-lg border border-dashed border-gray-200 py-4 text-center text-[11px] text-gray-300">
                  Drop here
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Add-stage column */}
        <div className="flex w-48 shrink-0 flex-col justify-start rounded-xl border border-dashed border-gray-300 bg-white/50 p-2">
          <form
            onSubmit={(e) => {
              e.preventDefault()
              if (!newStage.trim()) return
              void withToken((token) => addStage(jobId, newStage.trim(), token)).then(() =>
                setNewStage(''),
              )
            }}
            className="space-y-2"
          >
            <input
              value={newStage}
              onChange={(e) => setNewStage(e.target.value)}
              placeholder="New stage…"
              className="w-full rounded-lg border border-gray-300 bg-white px-2 py-1.5 text-xs shadow-sm focus:border-blue-400 focus:outline-none"
            />
            <button
              type="submit"
              disabled={!newStage.trim() || busy}
              className="w-full rounded-lg bg-gray-100 px-2 py-1.5 text-xs font-semibold text-gray-600 transition hover:bg-gray-200 disabled:opacity-50"
            >
              + Add stage
            </button>
          </form>
        </div>
      </div>
    </div>
  )
}
