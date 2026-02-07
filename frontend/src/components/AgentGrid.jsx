function timeSince(timestamp) {
  if (!timestamp) return 'never'
  const diff = (Date.now() - new Date(timestamp).getTime()) / 1000
  if (diff < 60) return `${Math.floor(diff)}s ago`
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`
  return `${Math.floor(diff / 3600)}h ago`
}

const agentColors = {
  'Claude-1': 'border-crt-cyan',
  'Claude-2': 'border-crt-magenta',
  'Claude-3': 'border-crt-green',
  'Claude-4': 'border-crt-amber',
}

const agentNeon = {
  'Claude-1': 'neon-cyan',
  'Claude-2': 'neon-magenta',
  'Claude-3': 'neon-green',
  'Claude-4': 'neon-amber',
}

const agentRoles = {
  'Claude-1': 'Backend/Core',
  'Claude-2': 'Frontend/UI',
  'Claude-3': 'Integration/Test',
  'Claude-4': 'Polish/Review',
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
                className={`p-3 rounded bg-retro-grid/50 border-l-2 ${agentColors[a.name] || 'border-zinc-600'}`}
              >
                <div className="flex items-center justify-between">
                  <span className={`text-sm font-medium font-mono ${agentNeon[a.name] || 'text-zinc-200'}`}>{a.name}</span>
                  <span className={`w-2 h-2 rounded-full ${isActive ? 'led-active animate-pulse' : 'led-inactive'}`} />
                </div>
                <div className="text-[11px] text-zinc-500 mt-1 font-mono">{agentRoles[a.name] || ''}</div>
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
