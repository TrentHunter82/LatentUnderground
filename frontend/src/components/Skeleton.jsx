function Bone({ className = '', style }) {
  return (
    <div className={`bg-retro-grid rounded animate-pulse ${className}`} style={style} />
  )
}

export function LogViewerSkeleton() {
  return (
    <div className="retro-panel border border-retro-border rounded flex flex-col h-full">
      <div className="flex items-center gap-2 px-3 py-2 border-b border-retro-border">
        <Bone className="h-6 w-10" />
        <Bone className="h-6 w-16" />
        <Bone className="h-6 w-16" />
        <Bone className="h-6 w-16" />
      </div>
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-retro-border">
        <Bone className="h-6 w-40" />
        <Bone className="h-5 w-8" />
        <Bone className="h-5 w-10" />
        <Bone className="h-5 w-10" />
      </div>
      <div className="flex-1 p-3 space-y-1 bg-retro-dark">
        {[...Array(12)].map((_, i) => (
          <Bone key={i} className="h-4" style={{ width: `${50 + Math.random() * 45}%` }} />
        ))}
      </div>
    </div>
  )
}

export function HistorySkeleton() {
  return (
    <div className="retro-panel rounded p-4">
      <Bone className="h-3 w-24 mb-3" />
      <div className="space-y-0">
        <div className="flex gap-4 py-2">
          <Bone className="h-3 w-20" />
          <Bone className="h-3 w-16" />
          <Bone className="h-3 w-16" />
          <Bone className="h-3 w-10 ml-auto" />
        </div>
        {[...Array(5)].map((_, i) => (
          <div key={i} className="flex gap-4 py-2 border-t border-retro-border">
            <Bone className="h-4 w-24" />
            <Bone className="h-4 w-16" />
            <Bone className="h-4 w-14" />
            <Bone className="h-4 w-8 ml-auto" />
          </div>
        ))}
      </div>
    </div>
  )
}

export function AnalyticsSkeleton() {
  return (
    <div className="p-4 space-y-4">
      <div className="flex gap-3 flex-wrap">
        {[0, 1, 2].map((i) => (
          <div key={i} className="retro-panel border border-retro-border rounded px-4 py-2">
            <Bone className="h-6 w-12 mb-1" />
            <Bone className="h-3 w-16" />
          </div>
        ))}
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="retro-panel border border-retro-border rounded p-3">
          <Bone className="h-3 w-32 mb-2" />
          <Bone className="h-24 w-full" />
        </div>
        <div className="retro-panel border border-retro-border rounded p-3">
          <Bone className="h-3 w-32 mb-2" />
          <Bone className="h-24 w-full" />
        </div>
      </div>
    </div>
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
