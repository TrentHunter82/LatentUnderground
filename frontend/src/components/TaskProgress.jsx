export default function TaskProgress({ tasks }) {
  const total = tasks?.total ?? 0
  const done = tasks?.done ?? 0
  const percent = tasks?.percent ?? 0

  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Task Progress</h3>
        <span className="text-sm font-mono text-zinc-300">
          {done}/{total} <span className="text-zinc-500">({Math.round(percent)}%)</span>
        </span>
      </div>

      {/* Progress bar */}
      <div className="retro-progress h-3 rounded" role="progressbar" aria-valuenow={percent} aria-valuemin={0} aria-valuemax={100} aria-label={`Task progress: ${done} of ${total} complete`}>
        <div
          className="retro-progress-fill h-full transition-all duration-500 ease-out"
          style={{
            width: `${percent}%`,
            background: percent === 100
              ? 'var(--color-crt-green)'
              : 'linear-gradient(90deg, var(--color-crt-green), var(--color-crt-cyan))',
          }}
        />
      </div>

      {/* Quick counts */}
      {total > 0 && (
        <div className="flex gap-4 mt-2 text-[11px] font-mono">
          <span className="text-crt-green">{done} done</span>
          <span className="text-zinc-500">{total - done} remaining</span>
        </div>
      )}
    </div>
  )
}
