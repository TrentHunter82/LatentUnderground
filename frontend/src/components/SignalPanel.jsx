const signalNames = ['backend-ready', 'frontend-ready', 'tests-passing', 'phase-complete']

const signalLabels = {
  'backend-ready': 'Backend Ready',
  'frontend-ready': 'Frontend Ready',
  'tests-passing': 'Tests Passing',
  'phase-complete': 'Phase Complete',
}

export default function SignalPanel({ signals, phase }) {
  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Signals</h3>

      {/* Phase indicator */}
      {phase && (
        <div className="mb-3 px-3 py-2 rounded bg-retro-grid/50 flex items-center justify-between border border-retro-border">
          <span className="text-xs text-zinc-400 font-mono">Phase</span>
          <span className="text-sm font-mono font-medium neon-green">
            {phase.Phase} / {phase.MaxPhases}
          </span>
        </div>
      )}

      {/* Signal list */}
      <div className="space-y-2">
        {signalNames.map((name) => {
          const active = signals?.[name] ?? false
          return (
            <div key={name} className="flex items-center gap-3 px-3 py-2 rounded bg-retro-grid/50">
              <div className={`w-3 h-3 rounded-full transition-colors ${
                active ? 'led-active' : 'led-inactive'
              }`} />
              <span className={`text-sm font-mono ${active ? 'text-zinc-200' : 'text-zinc-500'}`}>
                {signalLabels[name]}
              </span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
