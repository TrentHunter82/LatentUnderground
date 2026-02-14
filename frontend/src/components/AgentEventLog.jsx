import { useState, useEffect, useRef, useCallback } from 'react'
import { getAgentEvents } from '../lib/api'
import { AGENT_NEON_COLORS, AGENT_NAMES } from '../lib/constants'

const EVENT_ICONS = {
  agent_started: { icon: '▶', css: 'text-crt-green' },
  agent_stopped: { icon: '■', css: 'text-zinc-400' },
  agent_crashed: { icon: '✕', css: 'text-signal-red' },
  directive_queued: { icon: '→', css: 'text-crt-cyan' },
  directive_consumed: { icon: '✓', css: 'text-crt-green' },
  error_detected: { icon: '!', css: 'text-signal-red' },
  task_completed: { icon: '✓', css: 'text-crt-green' },
  output_milestone: { icon: '◆', css: 'text-crt-amber' },
  prompt_modified: { icon: '✎', css: 'text-crt-cyan' },
}

const EVENT_TYPES = [
  'all',
  'agent_started',
  'agent_stopped',
  'agent_crashed',
  'error_detected',
  'task_completed',
  'directive_queued',
  'directive_consumed',
  'output_milestone',
]

function formatEventTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  return d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export default function AgentEventLog({ projectId, wsEvents }) {
  const [events, setEvents] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [agentFilter, setAgentFilter] = useState(null)
  const [typeFilter, setTypeFilter] = useState('all')
  const listRef = useRef(null)
  const pollRef = useRef(null)

  const fetchEvents = useCallback(async () => {
    if (!projectId) return
    try {
      const filters = {}
      if (agentFilter) filters.agent = agentFilter
      if (typeFilter !== 'all') filters.event_type = typeFilter
      const data = await getAgentEvents(projectId, filters)
      setEvents(data.events || data || [])
      setError(null)
    } catch (e) {
      // Endpoint may not exist yet — graceful degradation
      if (!error) setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [projectId, agentFilter, typeFilter])

  useEffect(() => {
    setLoading(true)
    fetchEvents()

    // Poll every 5 seconds
    pollRef.current = setInterval(fetchEvents, 5000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [fetchEvents])

  // Refresh on relevant WS events
  useEffect(() => {
    if (!wsEvents) return
    if (['agent_event', 'directive_consumed', 'swarm_started', 'swarm_stopped'].includes(wsEvents.type)) {
      fetchEvents()
    }
  }, [wsEvents, fetchEvents])

  const getEventMeta = (type) => EVENT_ICONS[type] || { icon: '·', css: 'text-zinc-500' }

  if (loading) {
    return (
      <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Agent Events</h2>
        <div className="space-y-2">
          {[1, 2, 3, 4].map(i => (
            <div key={i} className="h-6 rounded bg-retro-grid/50 animate-pulse" style={{ animationDelay: `${i * 100}ms` }} />
          ))}
        </div>
      </div>
    )
  }

  return (
    <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4 animate-fade-in">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Agent Events</h2>
        <span className="text-[10px] text-zinc-600 font-mono">{events.length} events</span>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-1.5 mb-3">
        {/* Agent filter */}
        <select
          value={agentFilter || ''}
          onChange={(e) => setAgentFilter(e.target.value || null)}
          className="retro-input text-[11px] px-2 py-1 rounded"
          aria-label="Filter by agent"
        >
          <option value="">All Agents</option>
          {AGENT_NAMES.filter(n => n !== 'supervisor').map(name => (
            <option key={name} value={name}>{name}</option>
          ))}
        </select>

        {/* Type filter */}
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="retro-input text-[11px] px-2 py-1 rounded"
          aria-label="Filter by event type"
        >
          {EVENT_TYPES.map(t => (
            <option key={t} value={t}>{t === 'all' ? 'All Types' : t.replace(/_/g, ' ')}</option>
          ))}
        </select>
      </div>

      {error ? (
        <div className="text-zinc-600 text-sm py-4 text-center font-mono">
          Events not available yet
        </div>
      ) : events.length === 0 ? (
        <div className="text-zinc-600 text-sm py-4 text-center font-mono">No events recorded</div>
      ) : (
        <div ref={listRef} className="max-h-64 overflow-y-auto space-y-0.5" role="log" aria-label="Agent event timeline">
          {events.map((ev, i) => {
            const meta = getEventMeta(ev.event_type)
            const agentColor = AGENT_NEON_COLORS[ev.agent_name] || 'text-zinc-400'
            return (
              <div
                key={ev.id || i}
                className="flex items-start gap-2 px-2 py-1.5 rounded hover:bg-retro-grid/30 transition-colors text-[11px] font-mono"
              >
                <span className="text-[10px] text-zinc-600 shrink-0 w-16 tabular-nums" aria-label={`Time: ${formatEventTime(ev.timestamp)}`}>
                  {formatEventTime(ev.timestamp)}
                </span>
                <span className={`shrink-0 w-3 text-center ${meta.css}`} role="img" aria-label={ev.event_type.replace(/_/g, ' ')}>
                  {meta.icon}
                </span>
                <span className={`shrink-0 ${agentColor}`}>{ev.agent_name}</span>
                <span className="text-zinc-400 truncate flex-1">{ev.detail || ev.event_type.replace(/_/g, ' ')}</span>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
