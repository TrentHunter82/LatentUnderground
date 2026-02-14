import { memo, useState, useEffect, useCallback } from 'react'
import { AGENT_BORDER_COLORS, AGENT_NEON_COLORS, AGENT_ROLES } from '../lib/constants'
import { getDirectiveStatus } from '../lib/api'
import PromptEditorModal from './PromptEditorModal'

function timeSince(timestamp) {
  if (!timestamp) return 'never'
  const diff = (Date.now() - new Date(timestamp).getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

// Shape icons for color-independent status indication (WCAG 1.4.1)
function StatusIcon({ status, className = '' }) {
  const size = 10
  switch (status) {
    case 'running':
    case 'active':
      // Checkmark shape
      return (
        <svg width={size} height={size} viewBox="0 0 10 10" className={className} aria-hidden="true">
          <circle cx="5" cy="5" r="4.5" fill="currentColor" opacity="0.2" />
          <path d="M3 5l1.5 1.5L7 4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      )
    case 'crashed':
      // X shape
      return (
        <svg width={size} height={size} viewBox="0 0 10 10" className={className} aria-hidden="true">
          <circle cx="5" cy="5" r="4.5" fill="currentColor" opacity="0.2" />
          <path d="M3.5 3.5l3 3M6.5 3.5l-3 3" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      )
    default:
      // Dash shape (stopped/stale)
      return (
        <svg width={size} height={size} viewBox="0 0 10 10" className={className} aria-hidden="true">
          <circle cx="5" cy="5" r="4.5" fill="currentColor" opacity="0.2" />
          <path d="M3 5h4" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        </svg>
      )
  }
}

// Circuit breaker state badge
function CircuitBreakerBadge({ state }) {
  if (!state || state === 'closed') return null
  const isOpen = state === 'open'
  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[9px] font-mono ${
        isOpen
          ? 'bg-signal-red/15 text-signal-red border border-signal-red/30'
          : 'bg-signal-amber/15 text-signal-amber border border-signal-amber/30'
      }`}
      role="img"
      aria-label={`Circuit breaker ${state}`}
      title={isOpen ? 'Circuit breaker open — restarts blocked' : 'Circuit breaker half-open — probing'}
    >
      <svg width="10" height="10" viewBox="0 0 10 10" fill="none" aria-hidden="true">
        {isOpen ? (
          <>
            <circle cx="5" cy="5" r="4" stroke="currentColor" strokeWidth="1.2" />
            <path d="M3 5h1.5M5.5 5H7" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          </>
        ) : (
          <>
            <circle cx="5" cy="5" r="4" stroke="currentColor" strokeWidth="1.2" />
            <path d="M3 5h4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeDasharray="1 1.5" />
          </>
        )}
      </svg>
      {isOpen ? 'Open' : 'Half-open'}
    </span>
  )
}

function agentStatus(agent, processInfo) {
  // If we have process info, use it as ground truth
  if (processInfo) {
    if (processInfo.alive) return { label: 'Running', css: 'text-crt-green', led: 'led-active animate-pulse', shape: 'running' }
    if (processInfo.exit_code != null && processInfo.exit_code !== 0)
      return { label: `Crashed (exit ${processInfo.exit_code})`, css: 'text-signal-red', led: 'led-danger', shape: 'crashed' }
    return { label: 'Stopped', css: 'text-zinc-500', led: 'led-inactive', shape: 'stopped' }
  }
  // Fall back to heartbeat-based detection
  const age = agent.last_heartbeat
    ? (Date.now() - new Date(agent.last_heartbeat).getTime()) / 1000
    : Infinity
  if (age < 120) return { label: 'Active', css: 'text-crt-green', led: 'led-active animate-pulse', shape: 'active' }
  return { label: 'Stale', css: 'text-zinc-600', led: 'led-inactive', shape: 'stopped' }
}

export default memo(function AgentGrid({ agents, processAgents, projectId }) {
  const [directivePending, setDirectivePending] = useState({})
  const [promptEditor, setPromptEditor] = useState(null) // { agentName, prompt }

  // Build process info lookup by agent name
  const processMap = {}
  if (processAgents) {
    for (const pa of processAgents) {
      processMap[pa.name] = pa
    }
  }

  // Poll directive status for alive agents
  useEffect(() => {
    if (!projectId || !processAgents) return
    const aliveAgents = processAgents.filter(a => a.alive)
    if (aliveAgents.length === 0) return

    let cancelled = false
    const check = async () => {
      const pending = {}
      await Promise.all(aliveAgents.map(async (a) => {
        try {
          const data = await getDirectiveStatus(projectId, a.name)
          if (data.pending) pending[a.name] = true
        } catch {
          // Endpoint may not exist yet
        }
      }))
      if (!cancelled) setDirectivePending(pending)
    }
    check()
    const interval = setInterval(check, 5000)
    return () => { cancelled = true; clearInterval(interval) }
  }, [projectId, processAgents])

  const handleEditPrompt = useCallback((agentName) => {
    // We don't have the current prompt — the modal will need to be populated
    // by the parent or fetched. For now, open with empty and let the PUT endpoint handle it
    setPromptEditor({ agentName, prompt: '' })
  }, [])

  return (
    <div className="retro-panel retro-panel-glow rounded p-3 sm:p-4">
      <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-2 sm:mb-3 m-0 font-mono">Agents</h2>
      {!agents || agents.length === 0 ? (
        <div className="text-zinc-600 text-sm py-4 text-center">No agent data</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-2 gap-1.5 sm:gap-2" role="list" aria-label="Agent status list">
          {agents.map((a) => {
            const proc = processMap[a.name]
            const st = agentStatus(a, proc)
            const hasPendingDirective = directivePending[a.name]
            return (
              <div
                key={a.name}
                role="listitem"
                className={`group/card p-2 sm:p-3 rounded bg-retro-grid/50 border-l-2 ${AGENT_BORDER_COLORS[a.name] || 'border-zinc-600'} relative`}
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5">
                    <span className={`text-xs sm:text-sm font-medium font-mono ${AGENT_NEON_COLORS[a.name] || 'text-zinc-200'}`}>{a.name}</span>
                    {hasPendingDirective && (
                      <span
                        className="w-1.5 h-1.5 rounded-full bg-crt-amber animate-pulse"
                        role="img"
                        aria-label={`${a.name} has a pending directive`}
                        title="Directive pending"
                      />
                    )}
                  </div>
                  <div className="flex items-center gap-1">
                    <StatusIcon status={st.shape} className={st.css} />
                    <span className="sr-only">{`${a.name}: ${st.label.toLowerCase()}`}</span>
                    {projectId && (
                      <button
                        onClick={() => handleEditPrompt(a.name)}
                        className="text-[9px] text-zinc-600 hover:text-crt-cyan bg-transparent border-0 cursor-pointer opacity-0 group-hover/card:opacity-100 focus:opacity-100 transition-opacity p-1.5 -m-1 font-mono min-w-[28px] min-h-[28px] flex items-center justify-center"
                        title={`Edit ${a.name} prompt`}
                        aria-label={`Edit prompt for ${a.name}`}
                      >
                        ✎
                      </button>
                    )}
                  </div>
                </div>
                <div className="text-[10px] sm:text-[11px] text-zinc-500 mt-0.5 sm:mt-1 font-mono">{AGENT_ROLES[a.name] || ''}</div>
                <div className={`text-[10px] sm:text-[11px] mt-0.5 sm:mt-1 font-mono ${st.css}`}>
                  {st.label}
                  {proc?.pid && <span className="text-zinc-600 hidden sm:inline"> &middot; PID {proc.pid}</span>}
                  {a.last_heartbeat && <span className="text-zinc-600"> &middot; {timeSince(a.last_heartbeat)}</span>}
                </div>
                {proc?.circuit_state && proc.circuit_state !== 'closed' && (
                  <div className="mt-1">
                    <CircuitBreakerBadge state={proc.circuit_state} />
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}

      {promptEditor && (
        <PromptEditorModal
          open={!!promptEditor}
          projectId={projectId}
          agentName={promptEditor.agentName}
          currentPrompt={promptEditor.prompt}
          onClose={() => setPromptEditor(null)}
          onSaved={() => setPromptEditor(null)}
        />
      )}
    </div>
  )
})
