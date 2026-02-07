function Bone({ className = '' }) {
  return (
    <div className={`bg-retro-grid rounded animate-pulse ${className}`} />
  )
}

export function DashboardSkeleton() {
  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header skeleton */}
      <div className="px-6 py-4 border-b border-retro-border flex items-center justify-between">
        <div>
          <Bone className="h-6 w-48 mb-2" />
          <Bone className="h-4 w-72" />
        </div>
        <Bone className="h-9 w-24 rounded" />
      </div>

      {/* Grid skeleton */}
      <div className="p-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Task progress */}
        <div className="col-span-full retro-panel rounded p-4">
          <div className="flex items-center justify-between mb-2">
            <Bone className="h-3 w-24" />
            <Bone className="h-4 w-16" />
          </div>
          <Bone className="h-3 w-full rounded-full" />
        </div>

        {/* Agents */}
        <div className="retro-panel rounded p-4">
          <Bone className="h-3 w-16 mb-3" />
          <div className="grid grid-cols-2 gap-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="p-3 rounded bg-retro-grid/50">
                <Bone className="h-4 w-20 mb-2" />
                <Bone className="h-3 w-16 mb-1" />
                <Bone className="h-3 w-24" />
              </div>
            ))}
          </div>
        </div>

        {/* Signals */}
        <div className="retro-panel rounded p-4">
          <Bone className="h-3 w-16 mb-3" />
          <div className="space-y-2">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="flex items-center gap-3 px-3 py-2 rounded bg-retro-grid/50">
                <Bone className="w-3 h-3 rounded-full" />
                <Bone className="h-4 w-28" />
              </div>
            ))}
          </div>
        </div>

        {/* Activity */}
        <div className="col-span-full retro-panel rounded p-4">
          <Bone className="h-3 w-16 mb-3" />
          <div className="space-y-1 bg-retro-dark rounded p-3 border border-retro-border">
            {[0, 1, 2, 3, 4].map((i) => (
              <Bone key={i} className="h-4 w-full" style={{ width: `${70 + Math.random() * 30}%` }} />
            ))}
          </div>
        </div>
      </div>
    </div>
  )
}
