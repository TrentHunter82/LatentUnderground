import { AGENT_BORDER_COLORS, AGENT_NEON_COLORS, AGENT_ROLES } from '../lib/constants'

function timeSince(timestamp) {
  if (!timestamp) return 'never'
  const diff = (Date.now() - new Date(timestamp).getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

export default function AgentGrid({ agents }) {
  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Agents</h3>
      {!agents || agents.length === 0 ? (
        <div className="text-zinc-600 text-sm py-4 text-center">No agent data</div>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          {agents.map((a) => {
            const age = a.last_heartbeat
              ? (Date.now() - new Date(a.last_heartbeat).getTime()) / 1000
              : Infinity
            const isActive = age < 120
            return (
              <div
                key={a.name}
                className={`p-3 rounded bg-retro-grid/50 border-l-2 ${AGENT_BORDER_COLORS[a.name] || 'border-zinc-600'}`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium font-mono ${AGENT_NEON_COLORS[a.name] || 'text-zinc-200'}`}>{a.name}</span>
                  <span className={`w-2 h-2 rounded-full ${isActive ? 'led-active animate-pulse' : 'led-inactive'}`} />
                </div>
                <div className="text-[11px] text-zinc-500 mt-1 font-mono">{AGENT_ROLES[a.name] || ''}</div>
                <div className={`text-[11px] mt-1 font-mono ${isActive ? 'text-crt-green' : 'text-zinc-600'}`}>
                  {isActive ? 'Active' : 'Stale'} &middot; {timeSince(a.last_heartbeat)}
                </div>
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}
