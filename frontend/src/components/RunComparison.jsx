import { useState, useEffect } from 'react'
import { compareRuns } from '../lib/api'

function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function DeltaBadge({ value, unit = '', invert = false, metricName = '' }) {
  if (value == null || value === 0) return <span className="text-zinc-600 text-[10px]">—</span>
  const isPositive = value > 0
  // For duration, positive = slower = bad; for tasks, positive = more = good
  const isGood = invert ? !isPositive : isPositive
  const displayText = `${isPositive ? '+' : ''}${value}${unit}`
  const semanticLabel = `${metricName ? metricName + ': ' : ''}${displayText} (${isGood ? 'improvement' : 'regression'})`
  return (
    <span className={`text-[10px] font-mono px-1.5 py-0.5 rounded ${
      isGood ? 'text-crt-green bg-crt-green/10' : 'text-signal-red bg-signal-red/10'
    }`} aria-label={semanticLabel}>
      {displayText}
    </span>
  )
}

// Normalize API response or local comparison to a common shape
function normalizeComparison(raw) {
  if (!raw) return null
  // If data came from buildLocalComparison, it already has the right shape
  if (raw.deltas) return raw
  // API response shape: flat delta fields, run_a/run_b have duration_seconds
  return {
    run_a: {
      duration: raw.run_a?.duration_seconds ?? null,
      tasks: raw.run_a?.output_lines ?? null,
      status: raw.run_a?.status,
      crashes: raw.run_a?.error_count ?? 0,
    },
    run_b: {
      duration: raw.run_b?.duration_seconds ?? null,
      tasks: raw.run_b?.output_lines ?? null,
      status: raw.run_b?.status,
      crashes: raw.run_b?.error_count ?? 0,
    },
    deltas: {
      duration: raw.duration_delta_seconds ?? null,
      tasks: raw.output_lines_delta ?? null,
      crashes: raw.error_count_delta ?? null,
    },
    verdict: computeVerdict(raw),
  }
}

function computeVerdict(raw) {
  const errDelta = raw.error_count_delta ?? 0
  if (errDelta < 0) return 'improved'
  if (errDelta > 0) return 'regressed'
  const durDelta = raw.duration_delta_seconds
  if (durDelta != null && durDelta < -30) return 'improved'
  if (durDelta != null && durDelta > 30) return 'regressed'
  return 'similar'
}

export default function RunComparison({ runA, runB, onClose }) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!runA?.id || !runB?.id) return
    setLoading(true)
    compareRuns(runA.id, runB.id)
      .then(d => { setData(d); setError(null) })
      .catch(e => {
        // Endpoint may not exist — fall back to local comparison
        setData(buildLocalComparison(runA, runB))
        setError(null)
      })
      .finally(() => setLoading(false))
  }, [runA, runB])

  if (!runA || !runB) return null

  // Normalize to common shape (works for both API and local data)
  const comparison = normalizeComparison(data || buildLocalComparison(runA, runB))

  if (loading) {
    return (
      <div className="retro-panel rounded p-4 animate-fade-in">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Run Comparison</h2>
          {onClose && (
            <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 bg-transparent border-0 cursor-pointer text-sm" aria-label="Close comparison">✕</button>
          )}
        </div>
        <div className="space-y-2">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-8 rounded bg-retro-grid/50 animate-pulse" />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="retro-panel retro-panel-glow rounded p-4 animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Run Comparison</h2>
        {onClose && (
          <button onClick={onClose} className="text-zinc-500 hover:text-zinc-300 bg-transparent border-0 cursor-pointer text-sm" aria-label="Close comparison">✕</button>
        )}
      </div>

      {/* Verdict */}
      <div className={`text-center py-2 mb-3 rounded text-xs font-mono ${
        comparison.verdict === 'improved' ? 'text-crt-green bg-crt-green/10' :
        comparison.verdict === 'regressed' ? 'text-signal-red bg-signal-red/10' :
        'text-zinc-400 bg-retro-grid/30'
      }`}>
        {comparison.verdict === 'improved' ? 'Improved' :
         comparison.verdict === 'regressed' ? 'Regressed' :
         'Similar'}
      </div>

      {/* Comparison table */}
      <table className="w-full text-[11px] font-mono" role="table" aria-label="Run comparison details">
        <thead>
          <tr className="text-zinc-600 text-[10px] uppercase tracking-[0.15em]">
            <th className="text-left py-1.5 px-2 font-medium">Metric</th>
            <th className="text-right py-1.5 px-2 font-medium">Run A</th>
            <th className="text-right py-1.5 px-2 font-medium">Run B</th>
            <th className="text-right py-1.5 px-2 font-medium">Delta</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-t border-retro-border/50">
            <td className="py-1.5 px-2 text-zinc-400">Duration</td>
            <td className="py-1.5 px-2 text-right text-zinc-300">{formatDuration(comparison.run_a?.duration)}</td>
            <td className="py-1.5 px-2 text-right text-zinc-300">{formatDuration(comparison.run_b?.duration)}</td>
            <td className="py-1.5 px-2 text-right">
              <DeltaBadge value={comparison.deltas?.duration} unit="s" invert metricName="Duration" />
            </td>
          </tr>
          <tr className="border-t border-retro-border/50">
            <td className="py-1.5 px-2 text-zinc-400">Output Lines</td>
            <td className="py-1.5 px-2 text-right text-zinc-300">{comparison.run_a?.tasks ?? '—'}</td>
            <td className="py-1.5 px-2 text-right text-zinc-300">{comparison.run_b?.tasks ?? '—'}</td>
            <td className="py-1.5 px-2 text-right">
              <DeltaBadge value={comparison.deltas?.tasks} metricName="Output lines" />
            </td>
          </tr>
          <tr className="border-t border-retro-border/50">
            <td className="py-1.5 px-2 text-zinc-400">Status</td>
            <td className={`py-1.5 px-2 text-right ${comparison.run_a?.status === 'running' ? 'text-crt-green' : 'text-zinc-400'}`}>
              {comparison.run_a?.status || '—'}
            </td>
            <td className={`py-1.5 px-2 text-right ${comparison.run_b?.status === 'running' ? 'text-crt-green' : 'text-zinc-400'}`}>
              {comparison.run_b?.status || '—'}
            </td>
            <td className="py-1.5 px-2 text-right text-zinc-600">—</td>
          </tr>
          <tr className="border-t border-retro-border/50">
            <td className="py-1.5 px-2 text-zinc-400">Errors</td>
            <td className="py-1.5 px-2 text-right text-zinc-300">{comparison.run_a?.crashes ?? '—'}</td>
            <td className="py-1.5 px-2 text-right text-zinc-300">{comparison.run_b?.crashes ?? '—'}</td>
            <td className="py-1.5 px-2 text-right">
              <DeltaBadge value={comparison.deltas?.crashes} invert metricName="Errors" />
            </td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

function buildLocalComparison(runA, runB) {
  const durationA = runA.duration_seconds ?? null
  const durationB = runB.duration_seconds ?? null
  const tasksA = runA.tasks_completed ?? null
  const tasksB = runB.tasks_completed ?? null

  const durationDelta = durationA != null && durationB != null ? durationB - durationA : null
  const tasksDelta = tasksA != null && tasksB != null ? tasksB - tasksA : null

  // Simple verdict based on tasks and crashes
  let verdict = 'similar'
  if (tasksDelta != null && tasksDelta > 0) verdict = 'improved'
  else if (tasksDelta != null && tasksDelta < 0) verdict = 'regressed'

  return {
    run_a: { duration: durationA, tasks: tasksA, status: runA.status, crashes: 0 },
    run_b: { duration: durationB, tasks: tasksB, status: runB.status, crashes: 0 },
    deltas: { duration: durationDelta, tasks: tasksDelta, crashes: 0 },
    verdict,
  }
}
