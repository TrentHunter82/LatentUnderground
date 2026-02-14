import { useMemo, memo } from 'react'
import { AGENT_NEON_COLORS, AGENT_BORDER_COLORS } from '../lib/constants'

const STATUS_COLORS = {
  running: { bar: 'bg-crt-green', text: 'text-crt-green' },
  stopped: { bar: 'bg-zinc-600', text: 'text-zinc-500' },
  crashed: { bar: 'bg-signal-red', text: 'text-signal-red' },
}

function formatDuration(ms) {
  if (ms < 1000) return '<1s'
  const s = Math.floor(ms / 1000)
  if (s < 60) return `${s}s`
  const m = Math.floor(s / 60)
  const rem = s % 60
  if (m < 60) return `${m}m ${rem}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function agentState(agent) {
  if (agent.alive) return 'running'
  if (agent.exit_code != null && agent.exit_code !== 0) return 'crashed'
  return 'stopped'
}

export default memo(function AgentTimeline({ agents }) {
  const now = Date.now()

  const timelineData = useMemo(() => {
    if (!agents || agents.length === 0) return null

    const agentsWithTime = agents
      .filter(a => a.started_at)
      .map(a => {
        const startMs = new Date(a.started_at).getTime()
        const endMs = a.alive ? now : (startMs + (a.output_lines || 0) * 50) // rough estimate for ended agents
        return { ...a, startMs, endMs: Math.max(endMs, startMs + 1000), state: agentState(a) }
      })

    if (agentsWithTime.length === 0) return null

    const minStart = Math.min(...agentsWithTime.map(a => a.startMs))
    const maxEnd = Math.max(...agentsWithTime.map(a => a.endMs), now)
    const totalSpan = maxEnd - minStart || 1

    return {
      agents: agentsWithTime,
      minStart,
      maxEnd,
      totalSpan,
    }
  }, [agents, now])

  if (!timelineData) {
    return (
      <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Agent Timeline</h2>
        <div className="text-zinc-600 text-sm py-4 text-center">No agent timing data available</div>
      </div>
    )
  }

  const { agents: timeAgents, minStart, totalSpan } = timelineData

  return (
    <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4">
      <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Agent Timeline</h3>
      <div className="space-y-2" role="img" aria-label="Agent process timeline">
        {timeAgents.map((agent) => {
          const offsetPct = ((agent.startMs - minStart) / totalSpan) * 100
          const widthPct = Math.max(((agent.endMs - agent.startMs) / totalSpan) * 100, 1)
          const colors = STATUS_COLORS[agent.state]
          const duration = agent.alive ? now - agent.startMs : agent.endMs - agent.startMs
          const borderColor = AGENT_BORDER_COLORS[agent.name] || 'border-zinc-600'

          return (
            <div key={agent.name} className={`flex items-center gap-2 border-l-2 ${borderColor} pl-2`}>
              <span className={`text-[10px] sm:text-[11px] font-mono w-16 shrink-0 truncate ${AGENT_NEON_COLORS[agent.name] || 'text-zinc-400'}`}>
                {agent.name}
              </span>
              <div className="flex-1 h-5 bg-retro-grid/30 rounded relative overflow-hidden" title={`${agent.name}: ${agent.state} (${formatDuration(duration)})`}>
                <div
                  className={`absolute top-0 bottom-0 rounded ${colors.bar} ${agent.alive ? 'animate-pulse' : ''}`}
                  style={{ left: `${offsetPct}%`, width: `${widthPct}%`, minWidth: '4px' }}
                />
                {agent.state === 'crashed' && (
                  <div
                    className="absolute top-0 bottom-0 w-1 bg-signal-red"
                    style={{ left: `${offsetPct + widthPct}%` }}
                    title={`Crashed with exit code ${agent.exit_code}`}
                  />
                )}
              </div>
              <span className={`text-[10px] font-mono shrink-0 ${colors.text}`}>
                {formatDuration(duration)}
              </span>
            </div>
          )
        })}
      </div>
      <div className="flex justify-between mt-2 text-[9px] text-zinc-600 font-mono">
        <span>{new Date(minStart).toLocaleTimeString()}</span>
        <span>{new Date(now).toLocaleTimeString()}</span>
      </div>
    </div>
  )
})
