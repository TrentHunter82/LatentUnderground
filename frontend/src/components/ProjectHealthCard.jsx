import { useState, useEffect, useCallback } from 'react'
import { getProjectHealth, getSwarmHistory } from '../lib/api'

function HealthSparkline({ runs = [], width = 80, height = 20 }) {
  if (runs.length < 2) return null

  // Map runs to scores: success=1, stopped=0.5, failed=0
  const scores = runs.slice(0, 10).reverse().map(r => {
    if (r.status === 'completed') return 1
    if (r.status === 'stopped') return 0.5
    return 0
  })

  const step = width / (scores.length - 1)
  const points = scores.map((v, i) => `${i * step},${height - v * height}`).join(' ')

  return (
    <svg width={width} height={height} aria-hidden="true" className="inline-block">
      <polyline fill="none" stroke="#80C8B0" strokeWidth="1.5" strokeLinejoin="round" points={points} />
    </svg>
  )
}

function TrendArrow({ direction }) {
  if (direction === 'improving') {
    return (
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="#80C8B0" strokeWidth="1.5" strokeLinecap="round" aria-label="Improving" role="img">
        <path d="M5 8V2M2 4l3-2 3 2" />
      </svg>
    )
  }
  if (direction === 'degrading') {
    return (
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="#ef4444" strokeWidth="1.5" strokeLinecap="round" aria-label="Degrading" role="img">
        <path d="M5 2v6M2 6l3 2 3-2" />
      </svg>
    )
  }
  return (
    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" stroke="#a1a1aa" strokeWidth="1.5" strokeLinecap="round" aria-label="Stable" role="img">
      <path d="M2 5h6" />
    </svg>
  )
}

export default function ProjectHealthCard({ projectId, compact = false }) {
  const [health, setHealth] = useState(null)
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)

  const fetchHealth = useCallback(async () => {
    if (!projectId) return
    try {
      // Try the health endpoint first; fallback to computing from run history
      let healthData = null
      try {
        healthData = await getProjectHealth(projectId)
      } catch {
        // Endpoint may not exist yet; compute from runs
      }

      const historyData = await getSwarmHistory(projectId).catch(() => ({ runs: [] }))
      const allRuns = historyData.runs || []
      setRuns(allRuns)

      if (healthData) {
        setHealth(healthData)
      } else if (allRuns.length > 0) {
        // Compute health locally from last 10 runs
        const recentRuns = allRuns.slice(0, 10)
        const crashes = recentRuns.filter(r => r.status === 'failed').length
        const crashRate = (crashes / recentRuns.length) * 100
        const trend = computeTrend(recentRuns)
        const classification = crashRate > 30 ? 'critical' : crashRate > 10 ? 'warning' : 'healthy'

        setHealth({
          crash_rate: crashRate,
          trend,
          classification,
          total_runs: allRuns.length,
        })
      }
    } catch {
      // Silently fail
    } finally {
      setLoading(false)
    }
  }, [projectId])

  useEffect(() => {
    fetchHealth()
  }, [fetchHealth])

  if (loading) {
    return compact ? null : (
      <div className="retro-panel p-3 rounded animate-pulse">
        <div className="h-3 bg-retro-grid rounded w-1/2 mb-2" />
        <div className="h-3 bg-retro-grid rounded w-1/3" />
      </div>
    )
  }

  if (!health) return null

  const healthColors = {
    healthy: { dot: 'led-active', text: 'text-crt-green', label: 'Healthy' },
    warning: { dot: 'led-warning', text: 'text-signal-amber', label: 'Warning' },
    critical: { dot: 'led-danger', text: 'text-signal-red', label: 'Critical' },
  }
  const cfg = healthColors[health.classification] || healthColors.healthy

  if (compact) {
    return (
      <div className="flex items-center gap-1.5" title={`Health: ${cfg.label} (${health.crash_rate?.toFixed(0) ?? 0}% crash rate)`}>
        <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot}`} role="img" aria-label={`Health: ${cfg.label}`} />
        <TrendArrow direction={health.trend} />
      </div>
    )
  }

  return (
    <div className="retro-panel retro-panel-glow p-3 rounded">
      <div className="flex items-center justify-between mb-2">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-mono m-0">Project Health</h2>
        <div className="flex items-center gap-1.5">
          <span className={`w-2 h-2 rounded-full ${cfg.dot}`} role="img" aria-label={`Health: ${cfg.label}`} />
          <span className={`text-xs font-mono ${cfg.text}`}>{cfg.label}</span>
          <TrendArrow direction={health.trend} />
        </div>
      </div>
      <div className="grid grid-cols-3 gap-2 text-center">
        <div>
          <div className="text-[10px] text-zinc-500 font-mono">Crash Rate</div>
          <div className={`text-sm font-mono ${cfg.text}`}>{health.crash_rate?.toFixed(0) ?? 0}%</div>
        </div>
        <div>
          <div className="text-[10px] text-zinc-500 font-mono">Runs</div>
          <div className="text-sm font-mono text-zinc-200">{health.total_runs ?? runs.length}</div>
        </div>
        <div>
          <div className="text-[10px] text-zinc-500 font-mono">Last 10</div>
          <HealthSparkline runs={runs} />
        </div>
      </div>
    </div>
  )
}

function computeTrend(runs) {
  if (runs.length < 4) return 'stable'
  const half = Math.floor(runs.length / 2)
  const recent = runs.slice(0, half)
  const older = runs.slice(half)
  const recentFails = recent.filter(r => r.status === 'failed').length / recent.length
  const olderFails = older.filter(r => r.status === 'failed').length / older.length
  if (recentFails < olderFails - 0.1) return 'improving'
  if (recentFails > olderFails + 0.1) return 'degrading'
  return 'stable'
}
