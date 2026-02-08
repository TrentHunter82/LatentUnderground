import { useState } from 'react'
import { launchSwarm, stopSwarm } from '../lib/api'
import { useToast } from './Toast'
import ConfirmDialog from './ConfirmDialog'

export default function SwarmControls({ projectId, status, onAction }) {
  const [loading, setLoading] = useState(false)
  const [confirmStop, setConfirmStop] = useState(false)
  const toast = useToast()

  const handleLaunch = async (resume = false) => {
    setLoading(true)
    try {
      await launchSwarm({
        project_id: projectId,
        resume,
        no_confirm: true,
        agent_count: 4,
        max_phases: 24,
      })
      toast(resume ? 'Swarm resumed' : 'Swarm launched', 'success')
      onAction?.()
    } catch (e) {
      toast(`Launch failed: ${e.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    setConfirmStop(false)
    setLoading(true)
    try {
      await stopSwarm({ project_id: projectId })
      toast('Swarm stopped', 'success')
      onAction?.()
    } catch (e) {
      toast(`Stop failed: ${e.message}`, 'error')
    } finally {
      setLoading(false)
    }
  }

  return (
    <>
      <div className="flex gap-2">
        {status === 'running' ? (
          <button
            onClick={() => setConfirmStop(true)}
            disabled={loading}
            className="btn-neon btn-neon-danger px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            {loading ? 'Stopping...' : 'Stop Swarm'}
          </button>
        ) : (
          <>
            <button
              onClick={() => handleLaunch(false)}
              disabled={loading}
              className="btn-neon px-4 py-2 rounded text-sm disabled:opacity-50"
            >
              {loading ? 'Launching...' : 'Launch'}
            </button>
            {status === 'stopped' && (
              <button
                onClick={() => handleLaunch(true)}
                disabled={loading}
                className="px-4 py-2 rounded bg-retro-grid hover:bg-retro-border text-zinc-200 text-sm font-medium transition-colors disabled:opacity-50 cursor-pointer border border-retro-border font-mono"
              >
                Resume
              </button>
            )}
          </>
        )}
      </div>

      <ConfirmDialog
        open={confirmStop}
        title="Stop Swarm"
        message="This will terminate all running Claude agents. Are you sure you want to stop the swarm?"
        confirmLabel="Stop Swarm"
        danger
        onConfirm={handleStop}
        onCancel={() => setConfirmStop(false)}
      />
    </>
  )
}
