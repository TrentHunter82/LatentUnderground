import { memo } from 'react'
import { AGENT_NEON_COLORS } from '../lib/constants'

function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function ExitCodeBadge({ code }) {
  if (code == null) return <span className="text-zinc-500">—</span>
  if (code === 0) return <span className="text-crt-green">0</span>
  return <span className="text-signal-red font-medium">{code}</span>
}

export default memo(function RunSummary({ run, agents }) {
  if (!run) return null

  // Derive per-agent stats from run.summary if available (backend-computed)
  let summary = null
  if (run.summary) {
    if (typeof run.summary === 'string') {
      try { summary = JSON.parse(run.summary) } catch { /* malformed JSON */ }
    } else {
      summary = run.summary
    }
  }

  const hasAgents = agents && agents.length > 0
  const allSuccess = hasAgents ? agents.every(a => a.exit_code === 0 || a.exit_code == null) : (summary?.all_success ?? true)
  const totalCrashed = hasAgents ? agents.filter(a => a.exit_code != null && a.exit_code !== 0).length : (summary?.crashed_count ?? 0)

  return (
    <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4 animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Run Summary</h2>
        <span className={`text-xs font-mono px-2 py-0.5 rounded ${
          allSuccess ? 'text-crt-green bg-crt-green/10' : 'text-signal-red bg-signal-red/10'
        }`}>
          {allSuccess ? 'Success' : `${totalCrashed} crashed`}
        </span>
      </div>

      {/* Overall stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 mb-3">
        <div className="text-center p-2 rounded bg-retro-grid/30">
          <div className="text-lg font-mono text-zinc-200">{formatDuration(run.duration_seconds)}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider">Duration</div>
        </div>
        <div className="text-center p-2 rounded bg-retro-grid/30">
          <div className="text-lg font-mono text-zinc-200">{agents?.length || summary?.agent_count || '—'}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider">Agents</div>
        </div>
        <div className="text-center p-2 rounded bg-retro-grid/30">
          <div className="text-lg font-mono text-zinc-200">{run.tasks_completed ?? summary?.tasks_completed ?? '—'}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider">Tasks Done</div>
        </div>
        <div className="text-center p-2 rounded bg-retro-grid/30">
          <div className="text-lg font-mono text-zinc-200">{summary?.error_count ?? '—'}</div>
          <div className="text-[10px] text-zinc-600 uppercase tracking-wider">Errors</div>
        </div>
      </div>

      {/* Per-agent table */}
      {agents && agents.length > 0 && (
        <table className="w-full text-[11px] font-mono" role="table" aria-label="Per-agent run statistics">
          <thead>
            <tr className="text-zinc-600 text-[10px] uppercase tracking-[0.15em]">
              <th className="text-left py-1.5 px-2 font-medium">Agent</th>
              <th className="text-left py-1.5 px-2 font-medium">Status</th>
              <th className="text-right py-1.5 px-2 font-medium">Exit</th>
              <th className="text-right py-1.5 px-2 font-medium">Output</th>
            </tr>
          </thead>
          <tbody>
            {agents.map(a => {
              const agentColor = AGENT_NEON_COLORS[a.name] || 'text-zinc-300'
              const statusText = a.alive ? 'Running' : (a.exit_code != null && a.exit_code !== 0) ? 'Crashed' : 'Stopped'
              const statusCss = a.alive ? 'text-crt-green' : (a.exit_code != null && a.exit_code !== 0) ? 'text-signal-red' : 'text-zinc-500'
              return (
                <tr key={a.name} className="border-t border-retro-border/50">
                  <td className={`py-1.5 px-2 ${agentColor}`}>{a.name}</td>
                  <td className={`py-1.5 px-2 ${statusCss}`}>{statusText}</td>
                  <td className="py-1.5 px-2 text-right"><ExitCodeBadge code={a.exit_code} /></td>
                  <td className="py-1.5 px-2 text-right text-zinc-500">{a.output_lines ?? '—'}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </div>
  )
})
