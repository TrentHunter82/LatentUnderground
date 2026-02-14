import React, { useState, useEffect, lazy, Suspense } from 'react'
import { HistorySkeleton } from './Skeleton'
import { useSafeToast } from './Toast'

const RunComparison = lazy(() => import('./RunComparison'))

function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const statusColors = {
  running: 'neon-green',
  stopped: 'text-zinc-400',
  failed: 'text-signal-red',
  failed_guardrail: 'text-signal-red',
}

export default function SwarmHistory({ projectId, fetchHistory }) {
  const toast = useSafeToast()
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [compareSelection, setCompareSelection] = useState([]) // [runA, runB] or partial
  const [showComparison, setShowComparison] = useState(false)
  const [expandedRunId, setExpandedRunId] = useState(null)

  useEffect(() => {
    if (!projectId || !fetchHistory) return
    setLoading(true)
    fetchHistory(projectId)
      .then((data) => {
        setRuns(data.runs || [])
        setError(null)
      })
      .catch((e) => {
        setError(e.message)
        toast(`Failed to load history: ${e.message}`, 'error', 4000, {
          label: 'Retry',
          onClick: () => fetchHistory(projectId).then((data) => { setRuns(data.runs || []); setError(null) }).catch(() => {})
        })
      })
      .finally(() => setLoading(false))
  }, [projectId, fetchHistory])

  const toggleRunSelection = (run) => {
    setCompareSelection(prev => {
      const exists = prev.find(r => r.id === run.id)
      if (exists) return prev.filter(r => r.id !== run.id)
      if (prev.length >= 2) return [prev[1], run] // Replace oldest
      return [...prev, run]
    })
  }

  const canCompare = compareSelection.length === 2

  if (loading) {
    return <HistorySkeleton />
  }

  if (error) {
    return (
      <div className="retro-panel rounded p-4">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Run History</h3>
        <div className="text-signal-red text-sm py-4 text-center font-mono">{error}</div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="retro-panel retro-panel-glow rounded p-4 animate-fade-in">
        <div className="flex items-center justify-between mb-3">
          <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Run History</h3>
          <div className="flex items-center gap-2">
            {compareSelection.length > 0 && (
              <button
                onClick={() => setCompareSelection([])}
                className="text-[10px] text-zinc-600 hover:text-zinc-400 bg-transparent border-0 cursor-pointer font-mono"
              >
                Clear
              </button>
            )}
            {canCompare && (
              <button
                onClick={() => setShowComparison(true)}
                className="btn-neon px-2.5 py-1 rounded text-[10px]"
              >
                Compare ({compareSelection.length})
              </button>
            )}
            {!canCompare && runs.length >= 2 && (
              <span className="text-[10px] text-zinc-600 font-mono">
                {compareSelection.length === 0 ? 'Select 2 runs to compare' : '1 more to compare'}
              </span>
            )}
          </div>
        </div>
        {runs.length === 0 ? (
          <div className="text-zinc-600 text-sm py-4 text-center font-mono">No runs yet</div>
        ) : (
          <table className="w-full text-sm font-mono" role="table">
            <thead>
              <tr className="text-zinc-500 text-xs uppercase tracking-[0.15em]">
                {runs.length >= 2 && <th className="text-left py-2 px-1 font-medium w-8" scope="col">
                  <span className="text-[9px] text-zinc-600">Cmp</span>
                </th>}
                <th className="text-left py-2 px-2 font-medium">Started</th>
                <th className="text-left py-2 px-2 font-medium">Duration</th>
                <th className="text-left py-2 px-2 font-medium">Status</th>
                <th className="text-right py-2 px-2 font-medium">Tasks</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((run) => {
                const isSelected = compareSelection.some(r => r.id === run.id)
                const hasGuardrailResults = run.guardrail_results && run.guardrail_results.length > 0
                const isExpanded = expandedRunId === run.id
                return (
                  <React.Fragment key={run.id}>
                  <tr
                    className={`border-t border-retro-border cursor-pointer transition-colors ${isSelected ? 'bg-crt-cyan/5' : isExpanded ? 'bg-retro-grid/20' : 'hover:bg-retro-grid/30'}`}
                    onClick={() => runs.length >= 2 && toggleRunSelection(run)}
                  >
                    {runs.length >= 2 && (
                      <td className="py-2 px-2">
                        <input
                          type="checkbox"
                          checked={isSelected}
                          onChange={() => toggleRunSelection(run)}
                          onClick={(e) => e.stopPropagation()}
                          className="accent-crt-green w-3 h-3 cursor-pointer"
                          aria-label={`Select run from ${formatTime(run.started_at)} for comparison`}
                        />
                      </td>
                    )}
                    <td className="py-2 px-2 text-zinc-300">{formatTime(run.started_at)}</td>
                    <td className="py-2 px-2 text-zinc-400">{formatDuration(run.duration_seconds)}</td>
                    <td className={`py-2 px-2 ${statusColors[run.status] || 'text-zinc-400'}`}>
                      {run.status === 'failed_guardrail' ? (
                        <span className="inline-flex items-center gap-1" title="Run failed guardrail validation">
                          <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true" className="shrink-0">
                            <path d="M5 1l4 8H1L5 1z" stroke="currentColor" strokeWidth="1.2" strokeLinejoin="round" />
                            <path d="M5 4v2M5 7.5v.01" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
                          </svg>
                          guardrail
                        </span>
                      ) : run.status}
                    </td>
                    <td className="py-2 px-2 text-right text-zinc-400">
                      <span>{run.tasks_completed ?? 0}</span>
                      {hasGuardrailResults && (
                        <button
                          onClick={(e) => { e.stopPropagation(); setExpandedRunId(isExpanded ? null : run.id) }}
                          className="ml-2 p-0.5 rounded text-zinc-600 hover:text-crt-green bg-transparent border-0 cursor-pointer transition-colors inline-flex items-center"
                          aria-expanded={isExpanded}
                          aria-label={`${isExpanded ? 'Hide' : 'Show'} guardrail results for run from ${formatTime(run.started_at)}`}
                          title="View guardrail results"
                        >
                          <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" className={`transition-transform ${isExpanded ? 'rotate-180' : ''}`}>
                            <path d="M3 5l3 3 3-3" />
                          </svg>
                        </button>
                      )}
                    </td>
                  </tr>
                  {isExpanded && hasGuardrailResults && (
                    <tr className="border-t border-retro-border/50">
                      <td colSpan={runs.length >= 2 ? 5 : 4} className="px-3 py-3 bg-retro-dark/50">
                        <div className="text-[10px] uppercase tracking-[0.15em] text-zinc-500 font-medium mb-2">
                          Guardrail Validation — Run #{run.id}
                        </div>
                        <div className="space-y-1">
                          {run.guardrail_results.map((result, i) => {
                            const passed = result.passed
                            const isHalt = result.action === 'halt'
                            return (
                              <div
                                key={i}
                                className={`flex items-center gap-2 px-2 py-1 rounded text-xs font-mono ${
                                  passed
                                    ? 'bg-crt-green/5 text-crt-green'
                                    : isHalt
                                      ? 'bg-signal-red/10 text-signal-red'
                                      : 'bg-signal-amber/10 text-signal-amber'
                                }`}
                              >
                                {passed ? (
                                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden="true" className="shrink-0">
                                    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
                                    <path d="M3.5 6l2 2 3-3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                                  </svg>
                                ) : (
                                  <svg width="10" height="10" viewBox="0 0 12 12" fill="none" aria-hidden="true" className="shrink-0">
                                    <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
                                    <path d="M4 4l4 4M8 4l-4 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                                  </svg>
                                )}
                                <span className={`font-medium ${passed ? '' : 'text-inherit'}`}>
                                  {passed ? 'PASS' : 'FAIL'}
                                </span>
                                <span className="text-zinc-400">{result.rule_type}</span>
                                {result.pattern && <span className="text-zinc-600 truncate max-w-[120px]" title={result.pattern}>/{result.pattern}/</span>}
                                {result.threshold != null && <span className="text-zinc-600">≤{result.threshold}</span>}
                                <span className={`ml-auto text-[9px] px-1 py-0.5 rounded ${
                                  isHalt ? 'bg-signal-red/15 text-signal-red' : 'bg-signal-amber/15 text-signal-amber'
                                }`}>
                                  {result.action}
                                </span>
                                {result.detail && <span className="text-zinc-500 text-[10px] hidden sm:inline ml-1">{result.detail}</span>}
                              </div>
                            )
                          })}
                        </div>
                      </td>
                    </tr>
                  )}
                  </React.Fragment>
                )
              })}
            </tbody>
          </table>
        )}
      </div>

      {showComparison && canCompare && (
        <Suspense fallback={<div className="retro-panel p-3 text-center text-zinc-500 font-mono text-xs animate-pulse" role="status">Loading comparison...</div>}>
        <RunComparison
          runA={compareSelection[0]}
          runB={compareSelection[1]}
          onClose={() => setShowComparison(false)}
        />
        </Suspense>
      )}
    </div>
  )
}
