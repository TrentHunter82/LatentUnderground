import { useState, useEffect, useRef } from 'react'
import { getLogs } from '../lib/api'
import { AGENT_NEON_COLORS } from '../lib/constants'

export default function ActivityFeed({ projectId, wsEvents }) {
  const [logs, setLogs] = useState([])
  const bottomRef = useRef(null)

  // Initial load
  useEffect(() => {
    getLogs(projectId, 50)
      .then((data) => {
        const flat = (data.logs || []).flatMap((entry) =>
          entry.lines.map((line) => ({ agent: entry.agent, text: line }))
        )
        setLogs(flat.slice(-100))
      })
      .catch((e) => console.warn('Failed to load activity:', e))
  }, [projectId])

  // Append WebSocket log events
  useEffect(() => {
    if (wsEvents?.type === 'log') {
      setLogs((prev) => {
        const newEntries = wsEvents.lines.map((line) => ({
          agent: wsEvents.agent,
          text: line,
        }))
        return [...prev, ...newEntries].slice(-200)
      })
    }
  }, [wsEvents])

  // Auto-scroll
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Activity</h3>
      <div className="h-48 overflow-y-auto font-mono text-xs space-y-0.5 bg-retro-dark rounded p-3 border border-retro-border" role="log" aria-live="polite" aria-label="Activity feed">
        {logs.length === 0 && (
          <div className="text-zinc-600 text-center py-4">No activity yet</div>
        )}
        {logs.map((entry, i) => (
          <div key={`${entry.agent}-${i}`} className="leading-relaxed">
            <span className={`font-medium ${AGENT_NEON_COLORS[entry.agent] || 'text-zinc-500'}`}>
              [{entry.agent}]
            </span>{' '}
            <span className="text-zinc-400">{entry.text}</span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  )
}
