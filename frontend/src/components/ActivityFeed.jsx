import { useState, useEffect, useRef } from 'react'
import { AGENT_NEON_COLORS } from '../lib/constants'
import { useLogs } from '../hooks/useSwarmQuery'

export default function ActivityFeed({ projectId, wsEvents }) {
  const [logs, setLogs] = useState([])
  const bottomRef = useRef(null)

  // Initial load via TanStack Query
  const { data: logsData } = useLogs(projectId, 50, { enabled: !!projectId })

  useEffect(() => {
    if (logsData) {
      const flat = (logsData.logs || []).flatMap((entry) =>
        entry.lines.map((line) => ({ agent: entry.agent, text: line }))
      )
      setLogs(flat.slice(-100))
    }
  }, [logsData])

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
      <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Activity</h2>
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
