import { useMemo, useState, memo } from 'react'

const STATUS_COLORS = {
  completed: { bar: 'bg-crt-green', text: 'text-crt-green', label: 'Completed' },
  stopped: { bar: 'bg-crt-amber', text: 'text-crt-amber', label: 'Stopped' },
  running: { bar: 'bg-crt-cyan animate-pulse', text: 'text-crt-cyan', label: 'Running' },
  failed: { bar: 'bg-signal-red', text: 'text-signal-red', label: 'Failed' },
  failed_guardrail: { bar: 'bg-signal-red', text: 'text-signal-red', label: 'Guardrail' },
  crashed: { bar: 'bg-signal-red', text: 'text-signal-red', label: 'Crashed' },
}

function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function formatTime(dateStr) {
  if (!dateStr) return '—'
  try {
    const d = new Date(dateStr.replace(' ', 'T'))
    return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
  } catch { return dateStr }
}

export default memo(function ProjectStatusTimeline({ runs }) {
  const [expandedRun, setExpandedRun] = useState(null)

  const timelineData = useMemo(() => {
    if (!runs || runs.length === 0) return null

    const sorted = [...runs].sort((a, b) => {
      const aTime = new Date(a.started_at?.replace(' ', 'T') || 0).getTime()
      const bTime = new Date(b.started_at?.replace(' ', 'T') || 0).getTime()
      return aTime - bTime
    })

    const withTime = sorted.map(run => {
      const startMs = new Date(run.started_at?.replace(' ', 'T') || 0).getTime()
      const endMs = run.ended_at
        ? new Date(run.ended_at.replace(' ', 'T')).getTime()
        : (run.status === 'running' ? Date.now() : startMs + (run.duration_seconds || 60) * 1000)
      return { ...run, startMs, endMs: Math.max(endMs, startMs + 1000) }
    })

    const minStart = Math.min(...withTime.map(r => r.startMs))
    const maxEnd = Math.max(...withTime.map(r => r.endMs))
    const totalSpan = maxEnd - minStart || 1

    return { runs: withTime, minStart, maxEnd, totalSpan }
  }, [runs])

  if (!timelineData) {
    return (
      <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Status Timeline</h3>
        <div className="text-zinc-600 text-sm py-4 text-center">No run history yet</div>
      </div>
    )
  }

  const { runs: timeRuns, minStart, totalSpan } = timelineData

  return (
    <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Status Timeline</h3>
        <span className="text-[10px] text-zinc-600 font-mono">{timeRuns.length} run{timeRuns.length !== 1 ? 's' : ''}</span>
      </div>

      <div className="space-y-1.5" role="list" aria-label="Project run timeline">
        {timeRuns.map((run) => {
          const offsetPct = ((run.startMs - minStart) / totalSpan) * 100
          const widthPct = Math.max(((run.endMs - run.startMs) / totalSpan) * 100, 2)
          const colors = STATUS_COLORS[run.status] || STATUS_COLORS.stopped
          const isExpanded = expandedRun === run.id

          return (
            <div key={run.id} role="listitem">
              <button
                onClick={() => setExpandedRun(isExpanded ? null : run.id)}
                className="w-full flex items-center gap-2 bg-transparent border-0 cursor-pointer p-0 group text-left"
                aria-expanded={isExpanded}
                aria-label={`Run #${run.id}: ${colors.label}, ${formatDuration(run.duration_seconds)}`}
              >
                <span className="text-[10px] font-mono w-8 shrink-0 text-zinc-600 text-right">
                  #{run.id}
                </span>
                <div className="flex-1 h-5 bg-retro-grid/30 rounded relative overflow-hidden group-hover:bg-retro-grid/50 transition-colors">
                  <div
                    className={`absolute top-0 bottom-0 rounded ${colors.bar} transition-all`}
                    style={{ left: `${offsetPct}%`, width: `${widthPct}%`, minWidth: '6px' }}
                  />
                  {run.tasks_completed > 0 && widthPct > 8 && (
                    <span
                      className="absolute top-0 bottom-0 flex items-center text-[9px] font-mono text-zinc-900 font-semibold pointer-events-none"
                      style={{ left: `${offsetPct + 1}%` }}
                    >
                      {run.tasks_completed}
                    </span>
                  )}
                </div>
                <span className={`text-[10px] font-mono shrink-0 w-14 text-right ${colors.text}`}>
                  {formatDuration(run.duration_seconds)}
                </span>
              </button>

              {isExpanded && (
                <div className="ml-10 mt-1 mb-2 p-2 bg-retro-grid/20 rounded border border-retro-border text-[11px] font-mono space-y-1">
                  <div className="flex flex-wrap gap-x-4 gap-y-0.5 text-zinc-400">
                    <span>Started: <span className="text-zinc-300">{formatTime(run.started_at)}</span></span>
                    <span>Ended: <span className="text-zinc-300">{formatTime(run.ended_at)}</span></span>
                    <span>Status: <span className={colors.text}>{colors.label}</span></span>
                    {run.tasks_completed != null && (
                      <span>Tasks: <span className="text-zinc-300">{run.tasks_completed}</span></span>
                    )}
                    {run.phase != null && (
                      <span>Phase: <span className="text-zinc-300">{run.phase}</span></span>
                    )}
                  </div>
                  {run.label && (
                    <div className="text-crt-green">{run.label}</div>
                  )}
                  {run.notes && (
                    <div className="text-zinc-400 italic">{run.notes}</div>
                  )}
                  {run.task_summary && (
                    <div className="text-zinc-500 whitespace-pre-wrap">{run.task_summary}</div>
                  )}
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Time axis */}
      <div className="flex justify-between mt-2 text-[9px] text-zinc-600 font-mono">
        <span>{formatTime(timeRuns[0]?.started_at)}</span>
        <span>{formatTime(timeRuns[timeRuns.length - 1]?.ended_at || timeRuns[timeRuns.length - 1]?.started_at)}</span>
      </div>

      {/* Legend */}
      <div className="flex items-center gap-3 mt-2 flex-wrap">
        {Object.entries(STATUS_COLORS).map(([key, { bar, label }]) => (
          <div key={key} className="flex items-center gap-1">
            <div className={`w-2.5 h-2.5 rounded-sm ${bar.replace(' animate-pulse', '')}`} />
            <span className="text-[9px] text-zinc-600 font-mono">{label}</span>
          </div>
        ))}
      </div>
    </div>
  )
})
