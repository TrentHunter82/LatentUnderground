import { useState, useEffect, useCallback, useRef } from 'react'
import { getRunCheckpoints } from '../lib/api'
import { AGENT_NEON_COLORS, AGENT_BORDER_COLORS } from '../lib/constants'

const CHECKPOINT_COLORS = {
  task_complete: { bg: 'bg-crt-green', border: 'border-crt-green', label: 'Task Complete' },
  error: { bg: 'bg-signal-red', border: 'border-signal-red', label: 'Error' },
  directive_consumed: { bg: 'bg-blue-400', border: 'border-blue-400', label: 'Directive' },
  milestone: { bg: 'bg-zinc-400', border: 'border-zinc-400', label: 'Milestone' },
  task_start: { bg: 'bg-signal-amber', border: 'border-signal-amber', label: 'Task Start' },
}

function formatTime(timestamp) {
  if (!timestamp) return '—'
  try {
    const d = new Date(timestamp)
    return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch {
    return '—'
  }
}

function formatElapsed(seconds) {
  if (!seconds || seconds < 0) return '—'
  if (seconds < 60) return `${seconds.toFixed(0)}s`
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ${Math.floor(seconds % 60)}s`
  return `${Math.floor(seconds / 3600)}h ${Math.floor((seconds % 3600) / 60)}m`
}

export default function CheckpointTimeline({ runId, agents = [] }) {
  const [checkpoints, setCheckpoints] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [selectedCheckpoint, setSelectedCheckpoint] = useState(null)
  const [filterAgent, setFilterAgent] = useState('')
  const timelineRef = useRef(null)

  const fetchCheckpoints = useCallback(async () => {
    if (!runId) return
    try {
      const opts = filterAgent ? { agent: filterAgent } : {}
      const data = await getRunCheckpoints(runId, opts)
      setCheckpoints(Array.isArray(data) ? data : data?.checkpoints || [])
      setError(null)
    } catch (err) {
      if (err.message?.includes('404')) {
        setCheckpoints([])
        setError(null)
      } else {
        setError(err.message)
      }
    } finally {
      setLoading(false)
    }
  }, [runId, filterAgent])

  useEffect(() => {
    fetchCheckpoints()
  }, [fetchCheckpoints])

  if (!runId) return null

  if (loading) {
    return (
      <div className="retro-panel retro-panel-glow p-4 rounded animate-pulse">
        <div className="h-4 bg-retro-grid rounded w-1/3 mb-3" />
        <div className="h-8 bg-retro-grid rounded w-full" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="retro-panel p-3 text-xs text-signal-red font-mono">
        Checkpoints unavailable: {error}
      </div>
    )
  }

  // Compute timeline range
  const timestamps = checkpoints.map(c => new Date(c.timestamp).getTime()).filter(t => !isNaN(t))
  const minTime = timestamps.length > 0 ? Math.min(...timestamps) : 0
  const maxTime = timestamps.length > 0 ? Math.max(...timestamps) : 0
  const timeRange = maxTime - minTime || 1

  // Group by agent for lanes
  const agentNames = [...new Set(checkpoints.map(c => c.agent_name).filter(Boolean))]

  return (
    <div className="retro-panel retro-panel-glow p-4 rounded space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-mono m-0">Checkpoints</h2>
        {agentNames.length > 1 && (
          <select
            value={filterAgent}
            onChange={(e) => setFilterAgent(e.target.value)}
            className="retro-input text-[10px] px-2 py-0.5 rounded"
            aria-label="Filter checkpoints by agent"
          >
            <option value="">All Agents</option>
            {agentNames.map(name => (
              <option key={name} value={name}>{name}</option>
            ))}
          </select>
        )}
      </div>

      {checkpoints.length === 0 ? (
        <div className="text-xs text-zinc-600 font-mono py-2 text-center">
          No checkpoints recorded for this run
        </div>
      ) : (
        <>
          {/* Legend */}
          <div className="flex flex-wrap gap-2 text-[10px] font-mono">
            {Object.entries(CHECKPOINT_COLORS).map(([type, cfg]) => (
              <div key={type} className="flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full ${cfg.bg}`} role="img" aria-label={cfg.label} />
                <span className="text-zinc-500">{cfg.label}</span>
              </div>
            ))}
          </div>

          {/* Timeline */}
          <div ref={timelineRef} className="relative overflow-x-auto" role="list" aria-label="Checkpoint timeline">
            <div className="min-w-[400px]">
              {/* Time axis */}
              <div className="flex justify-between text-[9px] text-zinc-600 font-mono mb-1 px-1">
                <span>{formatTime(minTime)}</span>
                <span>{formatTime(maxTime)}</span>
              </div>

              {/* Agent lanes */}
              {agentNames.map((agentName, laneIdx) => {
                const agentCheckpoints = checkpoints.filter(c => c.agent_name === agentName)
                const colorIdx = parseInt(agentName.replace(/\D/g, '') || '1', 10) - 1

                return (
                  <div key={agentName} className="flex items-center gap-2 py-1.5 border-b border-retro-border/50 last:border-0" role="listitem">
                    <div className="w-16 shrink-0 text-[10px] font-mono truncate" style={{ color: AGENT_NEON_COLORS[agentName]?.color || '#80C8B0' }}>
                      {agentName}
                    </div>
                    <div className="flex-1 relative h-5">
                      {/* Track line */}
                      <div className="absolute top-1/2 left-0 right-0 h-px bg-retro-border" />

                      {/* Checkpoint markers */}
                      {agentCheckpoints.map((cp, i) => {
                        const t = new Date(cp.timestamp).getTime()
                        const pos = ((t - minTime) / timeRange) * 100
                        const cpColors = CHECKPOINT_COLORS[cp.checkpoint_type] || CHECKPOINT_COLORS.milestone

                        return (
                          <button
                            key={cp.id || i}
                            className={`absolute top-1/2 -translate-y-1/2 w-3 h-3 rounded-full border-2 ${cpColors.bg} ${cpColors.border} cursor-pointer transition-transform hover:scale-150 bg-transparent p-0 focus:outline-none focus:ring-2 focus:ring-crt-green`}
                            style={{ left: `${Math.min(Math.max(pos, 2), 98)}%` }}
                            onClick={() => setSelectedCheckpoint(selectedCheckpoint?.id === cp.id ? null : cp)}
                            aria-label={`${cpColors.label} at ${formatTime(cp.timestamp)}`}
                            title={`${cpColors.label}: ${formatTime(cp.timestamp)}`}
                          />
                        )
                      })}
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Detail panel */}
          {selectedCheckpoint && (
            <div className="retro-panel p-3 rounded space-y-2 animate-fade-in">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span className={`w-2.5 h-2.5 rounded-full ${(CHECKPOINT_COLORS[selectedCheckpoint.checkpoint_type] || CHECKPOINT_COLORS.milestone).bg}`} role="img" aria-label={selectedCheckpoint.checkpoint_type} />
                  <span className="text-xs font-mono text-zinc-200 capitalize">
                    {(CHECKPOINT_COLORS[selectedCheckpoint.checkpoint_type] || CHECKPOINT_COLORS.milestone).label}
                  </span>
                </div>
                <button
                  onClick={() => setSelectedCheckpoint(null)}
                  className="text-zinc-500 hover:text-zinc-300 bg-transparent border-0 cursor-pointer p-0.5 transition-colors"
                  aria-label="Close detail"
                >
                  <svg width="12" height="12" viewBox="0 0 12 12" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <path d="M3 9L9 3M3 3l6 6" />
                  </svg>
                </button>
              </div>
              <div className="grid grid-cols-2 gap-2 text-[10px] font-mono">
                <div>
                  <span className="text-zinc-500">Agent:</span>{' '}
                  <span className="text-zinc-300">{selectedCheckpoint.agent_name}</span>
                </div>
                <div>
                  <span className="text-zinc-500">Time:</span>{' '}
                  <span className="text-zinc-300">{formatTime(selectedCheckpoint.timestamp)}</span>
                </div>
                {selectedCheckpoint.data?.elapsed_time != null && (
                  <div>
                    <span className="text-zinc-500">Elapsed:</span>{' '}
                    <span className="text-zinc-300">{formatElapsed(selectedCheckpoint.data.elapsed_time)}</span>
                  </div>
                )}
                {selectedCheckpoint.data?.output_lines != null && (
                  <div>
                    <span className="text-zinc-500">Output Lines:</span>{' '}
                    <span className="text-zinc-300">{selectedCheckpoint.data.output_lines}</span>
                  </div>
                )}
              </div>
              {selectedCheckpoint.data?.last_lines?.length > 0 && (
                <div className="mt-1">
                  <div className="text-[10px] text-zinc-500 font-mono mb-1">Output Preview:</div>
                  <pre className="text-[10px] font-mono text-zinc-400 bg-retro-dark p-2 rounded max-h-20 overflow-y-auto whitespace-pre-wrap m-0">
                    {selectedCheckpoint.data.last_lines.join('\n')}
                  </pre>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
