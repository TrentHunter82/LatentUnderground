import { useState, useEffect, useCallback, memo } from 'react'
import { getSwarmHistory, getProjectStats } from '../lib/api'
import { AnalyticsSkeleton } from './Skeleton'

const statusColors = {
  completed: '#80C8B0',
  failed: '#C41E3A',
  stopped: '#E87838',
  running: '#5AACA0',
}

function formatDuration(seconds) {
  if (seconds == null) return '--'
  if (seconds < 60) return `${Math.round(seconds)}s`
  const m = Math.floor(seconds / 60)
  const s = Math.round(seconds % 60)
  return `${m}m ${s}s`
}

function RunTrendChart({ runs }) {
  const last20 = runs.slice(-20)
  if (last20.length === 0) return null

  const maxTasks = Math.max(...last20.map((r) => r.tasks_completed || 0), 1)
  const barWidth = Math.max(8, Math.floor(280 / last20.length) - 2)
  const chartWidth = last20.length * (barWidth + 2)
  const chartHeight = 100

  return (
    <div className="retro-panel border border-retro-border rounded p-3">
      <div className="text-xs font-mono text-zinc-500 mb-2">Tasks per Run (last {last20.length})</div>
      <svg width={chartWidth} height={chartHeight} role="img" aria-label={`Bar chart: ${last20.length} runs`}>
        {last20.map((run, i) => {
          const h = ((run.tasks_completed || 0) / maxTasks) * (chartHeight - 16)
          const color = statusColors[run.status] || '#5AACA0'
          return (
            <g key={run.id || i}>
              <rect
                x={i * (barWidth + 2)}
                y={chartHeight - h - 8}
                width={barWidth}
                height={Math.max(h, 2)}
                fill={color}
                rx={1}
                opacity={0.85}
              />
              <title>Run {run.id}: {run.tasks_completed || 0} tasks ({run.status})</title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function PhaseTimeline({ runs }) {
  const completed = runs.filter((r) => r.duration_seconds > 0)
  if (completed.length === 0) return null

  const maxDuration = Math.max(...completed.map((r) => r.duration_seconds))
  const timelineWidth = 320

  return (
    <div className="retro-panel border border-retro-border rounded p-3">
      <div className="text-xs font-mono text-zinc-500 mb-2">Run Duration Timeline</div>
      <svg width={timelineWidth} height={completed.length * 20 + 4} role="img" aria-label="Phase timeline">
        {completed.map((run, i) => {
          const w = Math.max((run.duration_seconds / maxDuration) * (timelineWidth - 60), 4)
          const color = statusColors[run.status] || '#5AACA0'
          return (
            <g key={run.id || i}>
              <rect x={0} y={i * 20 + 2} width={w} height={14} fill={color} rx={2} opacity={0.8} />
              <text x={w + 4} y={i * 20 + 13} fill="#71717a" fontSize="10" fontFamily="monospace">
                {formatDuration(run.duration_seconds)}
              </text>
              <title>Run {run.id}: {formatDuration(run.duration_seconds)}</title>
            </g>
          )
        })}
      </svg>
    </div>
  )
}

function AgentEfficiencyBars({ stats }) {
  const metrics = [
    { label: 'Total Runs', value: stats.total_runs || 0, max: Math.max(stats.total_runs || 0, 10), color: '#5AACA0' },
    { label: 'Tasks Done', value: stats.total_tasks_completed || 0, max: Math.max(stats.total_tasks_completed || 0, 20), color: '#80C8B0' },
  ]

  return (
    <div className="retro-panel border border-retro-border rounded p-3">
      <div className="text-xs font-mono text-zinc-500 mb-2">Metrics</div>
      <div className="space-y-2">
        {metrics.map((m) => (
          <div key={m.label}>
            <div className="flex justify-between text-[10px] font-mono text-zinc-400 mb-0.5">
              <span>{m.label}</span>
              <span>{m.value}</span>
            </div>
            <div className="h-2 bg-retro-grid rounded overflow-hidden">
              <div
                className="h-full rounded transition-all"
                style={{ width: `${Math.min((m.value / m.max) * 100, 100)}%`, backgroundColor: m.color }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

export default memo(function Analytics({ projectId }) {
  const [runs, setRuns] = useState([])
  const [stats, setStats] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const loadData = useCallback(() => {
    setLoading(true)
    setError(null)

    Promise.all([
      getSwarmHistory(projectId),
      getProjectStats(projectId),
    ]).then(([historyData, statsData]) => {
      setRuns(historyData.runs || [])
      setStats(statsData)
      setLoading(false)
    }).catch((e) => {
      setError(e.message)
      setLoading(false)
    })
  }, [projectId])

  useEffect(() => {
    loadData()
  }, [loadData])

  if (loading) {
    return <AnalyticsSkeleton />
  }

  if (error) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="retro-panel border border-retro-border rounded p-6 text-center max-w-sm">
          <div className="text-signal-red text-sm font-mono mb-3">{error}</div>
          <button
            onClick={loadData}
            className="btn-neon px-4 py-2 rounded text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (runs.length === 0) {
    return (
      <div className="p-6 text-center">
        <div className="text-zinc-500 font-mono text-sm">
          Waiting for data — Analytics will appear after your first swarm run completes.
        </div>
      </div>
    )
  }

  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full animate-fade-in">
      {/* Summary chips */}
      <div className="flex gap-3 flex-wrap">
        <div className="retro-panel border border-retro-border rounded px-4 py-2 text-center">
          <div className="text-lg font-bold neon-green font-mono">{stats?.total_runs ?? runs.length}</div>
          <div className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider">Total Runs</div>
        </div>
        <div className="retro-panel border border-retro-border rounded px-4 py-2 text-center">
          <div className="text-lg font-bold neon-cyan font-mono">
            {formatDuration(stats?.avg_duration_seconds)}
          </div>
          <div className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider">Avg Duration</div>
        </div>
        <div className="retro-panel border border-retro-border rounded px-4 py-2 text-center">
          <div className="text-lg font-bold neon-amber font-mono">{stats?.total_tasks_completed ?? 0}</div>
          <div className="text-[10px] text-zinc-500 font-mono uppercase tracking-wider">Tasks Done</div>
        </div>
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <RunTrendChart runs={runs} />
        <PhaseTimeline runs={runs} />
      </div>

      {stats && <AgentEfficiencyBars stats={stats} />}
    </div>
  )
})
