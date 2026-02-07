import { useState, useEffect, useRef, useCallback } from 'react'
import { getLogs } from '../lib/api'

const agents = ['Claude-1', 'Claude-2', 'Claude-3', 'Claude-4', 'supervisor']

const agentColors = {
  'Claude-1': { label: 'neon-cyan', bg: 'bg-crt-cyan/5' },
  'Claude-2': { label: 'neon-magenta', bg: 'bg-crt-magenta/5' },
  'Claude-3': { label: 'neon-green', bg: 'bg-crt-green/5' },
  'Claude-4': { label: 'neon-amber', bg: 'bg-crt-amber/5' },
  'supervisor': { label: 'text-zinc-400', bg: 'bg-zinc-500/5' },
}

export default function LogViewer({ projectId, wsEvents }) {
  const [logs, setLogs] = useState([])
  const [filter, setFilter] = useState('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const containerRef = useRef(null)

  // Load initial logs
  const loadLogs = useCallback(async () => {
    try {
      const data = await getLogs(projectId, 200)
      const flat = (data.logs || []).flatMap((entry) =>
        entry.lines.map((line, i) => ({
          id: `${entry.agent}-${i}-${Date.now()}`,
          agent: entry.agent,
          text: line,
        }))
      )
      setLogs(flat)
    } catch {}
  }, [projectId])

  useEffect(() => {
    loadLogs()
  }, [loadLogs])

  // Append WebSocket log events
  useEffect(() => {
    if (wsEvents?.type === 'log') {
      const newEntries = wsEvents.lines.map((line, i) => ({
        id: `${wsEvents.agent}-ws-${Date.now()}-${i}`,
        agent: wsEvents.agent,
        text: line,
      }))
      setLogs((prev) => [...prev, ...newEntries].slice(-1000))
    }
  }, [wsEvents])

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  const filtered = filter === 'all' ? logs : logs.filter((l) => l.agent === filter)

  return (
    <div className="retro-panel border border-retro-border rounded flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-retro-border flex-wrap">
        <button
          onClick={() => setFilter('all')}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer border-0 font-mono ${
            filter === 'all' ? 'bg-retro-grid text-crt-green border border-crt-green/30' : 'text-zinc-500 hover:text-zinc-300 bg-transparent'
          }`}
        >
          All
        </button>
        {agents.map((a) => (
          <button
            key={a}
            onClick={() => setFilter(a)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer border-0 font-mono ${
              filter === a ? 'bg-retro-grid text-zinc-100' : `${agentColors[a]?.label || 'text-zinc-500'} hover:bg-retro-grid bg-transparent`
            }`}
          >
            {a}
          </button>
        ))}

        <div className="flex-1" />

        <label className="flex items-center gap-1.5 text-xs text-zinc-500 cursor-pointer font-mono">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-crt-green"
          />
          Auto-scroll
        </label>
      </div>

      {/* Log output */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto font-mono text-xs p-3 min-h-48 bg-retro-dark"
      >
        {filtered.length === 0 && (
          <div className="text-zinc-600 text-center py-8">No logs</div>
        )}
        {filtered.map((entry) => {
          const color = agentColors[entry.agent] || { label: 'text-zinc-500', bg: '' }
          return (
            <div key={entry.id} className={`py-0.5 px-2 rounded ${color.bg}`}>
              <span className={`font-semibold ${color.label}`}>[{entry.agent}]</span>{' '}
              <span className="text-zinc-400">{entry.text}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
