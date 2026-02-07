import { useState, useEffect } from 'react'

function formatDuration(seconds) {
  if (seconds == null) return '—'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  if (m < 60) return `${m}m ${s}s`
  const h = Math.floor(m / 60)
  return `${h}h ${m % 60}m`
}

function formatTime(iso) {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleString(undefined, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })
}

const statusColors = {
  running: 'neon-green',
  stopped: 'text-zinc-400',
  failed: 'text-signal-red',
}

export default function SwarmHistory({ projectId, fetchHistory }) {
  const [runs, setRuns] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!projectId || !fetchHistory) return
    setLoading(true)
    fetchHistory(projectId)
      .then((data) => {
        setRuns(data.runs || [])
        setError(null)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [projectId, fetchHistory])

  if (loading) {
    return (
      <div className="retro-panel rounded p-4">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Run History</h3>
        <div className="text-zinc-600 text-sm py-4 text-center font-mono">Loading...</div>
      </div>
    )
  }

  if (error) {
    return (
      <div className="retro-panel rounded p-4">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Run History</h3>
        <div className="text-signal-red text-sm py-4 text-center font-mono">{error}</div>
      </div>
    )
  }

  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">Run History</h3>
      {runs.length === 0 ? (
        <div className="text-zinc-600 text-sm py-4 text-center font-mono">No runs yet</div>
      ) : (
        <table className="w-full text-sm font-mono" role="table">
          <thead>
            <tr className="text-zinc-500 text-xs uppercase tracking-[0.15em]">
              <th className="text-left py-2 px-2 font-medium">Started</th>
              <th className="text-left py-2 px-2 font-medium">Duration</th>
              <th className="text-left py-2 px-2 font-medium">Status</th>
              <th className="text-right py-2 px-2 font-medium">Tasks</th>
            </tr>
          </thead>
          <tbody>
            {runs.map((run) => (
              <tr key={run.id} className="border-t border-retro-border">
                <td className="py-2 px-2 text-zinc-300">{formatTime(run.started_at)}</td>
                <td className="py-2 px-2 text-zinc-400">{formatDuration(run.duration_seconds)}</td>
                <td className={`py-2 px-2 ${statusColors[run.status] || 'text-zinc-400'}`}>{run.status}</td>
                <td className="py-2 px-2 text-right text-zinc-400">{run.tasks_completed ?? 0}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
