import { useState, useEffect, useRef, useCallback } from 'react'
import { getSystemInfo, getSystemHealth, getMetrics } from '../lib/api'

function GaugeBar({ label, value, max = 100, unit = '%', warningAt = 80, criticalAt = 90 }) {
  const pct = max > 0 ? Math.min((value / max) * 100, 100) : 0
  const color = pct >= criticalAt ? 'bg-signal-red' : pct >= warningAt ? 'bg-signal-amber' : 'bg-crt-green'

  return (
    <div className="space-y-1">
      <div className="flex items-center justify-between text-xs font-mono">
        <span className="text-zinc-400">{label}</span>
        <span className="text-zinc-300">{typeof value === 'number' ? value.toFixed(1) : '—'}{unit}</span>
      </div>
      <div className="h-2 bg-retro-grid rounded-full overflow-hidden" role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100} aria-label={`${label}: ${typeof value === 'number' ? value.toFixed(1) : 0}${unit}`}>
        <div className={`h-full rounded-full transition-all duration-500 ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

function Sparkline({ data, width = 120, height = 24, color = '#80C8B0' }) {
  if (!data || data.length < 2) return <span className="text-[10px] text-zinc-600 font-mono">No data</span>

  const min = Math.min(...data)
  const max = Math.max(...data)
  const range = max - min || 1
  const step = width / (data.length - 1)

  const points = data.map((v, i) => `${i * step},${height - ((v - min) / range) * height}`).join(' ')

  return (
    <svg width={width} height={height} aria-hidden="true" className="inline-block">
      <polyline fill="none" stroke={color} strokeWidth="1.5" strokeLinejoin="round" points={points} />
    </svg>
  )
}

function formatUptime(seconds) {
  if (!seconds || seconds < 0) return '—'
  const d = Math.floor(seconds / 86400)
  const h = Math.floor((seconds % 86400) / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  if (d > 0) return `${d}d ${h}h`
  if (h > 0) return `${h}h ${m}m`
  return `${m}m`
}

function formatBytes(bytes) {
  if (!bytes || bytes < 0) return '—'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function parsePrometheusMetrics(text) {
  const result = { requestCount: 0, errorRate: 0, avgLatency: 0, requestHistory: [] }
  if (!text || typeof text !== 'string') return result

  const lines = text.split('\n')
  for (const line of lines) {
    if (line.startsWith('#') || !line.trim()) continue
    const match = line.match(/^(\w+)(?:\{[^}]*\})?\s+([\d.eE+-]+)$/)
    if (!match) continue
    const [, name, val] = match
    const num = parseFloat(val)

    if (name === 'lu_http_requests_total') result.requestCount += num
    if (name === 'lu_http_duration_seconds_sum') result.avgLatency = num
    if (name === 'lu_http_duration_seconds_count') result.latencyCount = num
    if (name === 'lu_active_agents') result.activeAgents = num
    if (name === 'lu_active_projects') result.activeProjects = num
    if (name === 'lu_db_size_bytes') result.dbSizeBytes = num
  }

  if (result.latencyCount > 0) {
    result.avgLatency = (result.avgLatency / result.latencyCount) * 1000 // ms
  }

  return result
}

export default function OperationsDashboard() {
  const [system, setSystem] = useState(null)
  const [health, setHealth] = useState(null)
  const [metrics, setMetrics] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [lastRefresh, setLastRefresh] = useState(null)
  const intervalRef = useRef(null)
  const requestHistoryRef = useRef([])

  const fetchData = useCallback(async () => {
    try {
      const [sysData, healthData, metricsText] = await Promise.allSettled([
        getSystemInfo(),
        getSystemHealth(),
        fetch('/api/metrics').then(r => r.ok ? r.text() : ''),
      ])

      if (sysData.status === 'fulfilled') setSystem(sysData.value)
      if (healthData.status === 'fulfilled') setHealth(healthData.value)
      if (metricsText.status === 'fulfilled') {
        const parsed = parsePrometheusMetrics(metricsText.value)
        // Track request count history for sparkline
        requestHistoryRef.current = [...requestHistoryRef.current.slice(-59), parsed.requestCount]
        parsed.requestHistory = requestHistoryRef.current
        setMetrics(parsed)
      }

      setError(null)
      setLastRefresh(new Date())
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()
    intervalRef.current = setInterval(fetchData, 10000)
    return () => { if (intervalRef.current) clearInterval(intervalRef.current) }
  }, [fetchData])

  if (loading && !system) {
    return (
      <div className="space-y-4 animate-pulse">
        {[1, 2, 3].map(i => (
          <div key={i} className="retro-panel p-4 rounded">
            <div className="h-4 bg-retro-grid rounded w-1/3 mb-3" />
            <div className="space-y-2">
              <div className="h-3 bg-retro-grid rounded w-full" />
              <div className="h-3 bg-retro-grid rounded w-2/3" />
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold neon-green m-0 font-mono uppercase tracking-widest">Operations</h2>
        <div className="flex items-center gap-2">
          {lastRefresh && (
            <span className="text-[10px] text-zinc-600 font-mono">
              Updated {lastRefresh.toLocaleTimeString()}
            </span>
          )}
          <button
            onClick={fetchData}
            className="p-1 rounded text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
            aria-label="Refresh operations data"
            title="Refresh"
          >
            <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M1 8a7 7 0 0113.36-2.87M15 8a7 7 0 01-13.36 2.87" />
              <path d="M14.5 1v4h-4M1.5 15v-4h4" />
            </svg>
          </button>
        </div>
      </div>

      {error && (
        <div className="retro-panel p-3 border-signal-red/30 text-xs text-signal-red font-mono">
          Failed to fetch: {error}
        </div>
      )}

      {/* System Metrics */}
      <section>
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-mono mb-2">System Resources</h3>
        <div className="retro-panel retro-panel-glow p-4 rounded space-y-3">
          <GaugeBar label="CPU" value={system?.cpu_percent ?? 0} />
          <GaugeBar label="Memory" value={system?.memory_percent ?? 0} />
          <GaugeBar label="Disk" value={system?.disk_percent ?? 0} />
          <div className="grid grid-cols-2 gap-3 pt-2 border-t border-retro-border">
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Uptime</div>
              <div className="text-sm text-zinc-200 font-mono">{formatUptime(system?.uptime_seconds)}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Active Agents</div>
              <div className="text-sm text-zinc-200 font-mono">{metrics?.activeAgents ?? 0}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Python</div>
              <div className="text-sm text-zinc-200 font-mono">{system?.python_version || '—'}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">CPU Cores</div>
              <div className="text-sm text-zinc-200 font-mono">{system?.cpu_count ?? '—'}</div>
            </div>
          </div>
        </div>
      </section>

      {/* Database Health */}
      <section>
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-mono mb-2">Database</h3>
        <div className="retro-panel retro-panel-glow p-4 rounded">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">DB Size</div>
              <div className="text-sm text-zinc-200 font-mono">{formatBytes(system?.db_size_bytes ?? metrics?.dbSizeBytes)}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Schema Version</div>
              <div className="text-sm text-zinc-200 font-mono">v{health?.db?.schema_version ?? '—'}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Status</div>
              <div className="flex items-center gap-1.5">
                <span className={`w-2 h-2 rounded-full ${health?.status === 'ok' ? 'led-active' : 'led-danger'}`} role="img" aria-label={`Database ${health?.status === 'ok' ? 'healthy' : 'unhealthy'}`} />
                <span className="text-sm text-zinc-200 font-mono capitalize">{health?.status ?? '—'}</span>
              </div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Active Projects</div>
              <div className="text-sm text-zinc-200 font-mono">{metrics?.activeProjects ?? health?.active_processes ?? 0}</div>
            </div>
          </div>
        </div>
      </section>

      {/* Request Metrics */}
      <section>
        <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-mono mb-2">Request Metrics</h3>
        <div className="retro-panel retro-panel-glow p-4 rounded space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Total Requests</div>
              <div className="text-sm text-zinc-200 font-mono">{metrics?.requestCount?.toLocaleString() ?? '—'}</div>
            </div>
            <div>
              <div className="text-[10px] text-zinc-500 font-mono">Avg Latency</div>
              <div className="text-sm text-zinc-200 font-mono">{metrics?.avgLatency ? `${metrics.avgLatency.toFixed(1)}ms` : '—'}</div>
            </div>
          </div>
          <div>
            <div className="text-[10px] text-zinc-500 font-mono mb-1">Request Volume (last 60 samples)</div>
            <Sparkline data={metrics?.requestHistory} />
          </div>
        </div>
      </section>
    </div>
  )
}
