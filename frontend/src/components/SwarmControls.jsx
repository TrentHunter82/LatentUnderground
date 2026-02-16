import { useState } from 'react'
import { useLaunchSwarm, useStopSwarm, useSendDirective, useUpdateProjectConfig } from '../hooks/useMutations'
import { useToast } from './Toast'
import { useNotifications } from '../hooks/useNotifications'
import ConfirmDialog from './ConfirmDialog'

export default function SwarmControls({ projectId, status, config, onAction, agents }) {
  const [loadingAction, setLoadingAction] = useState(null) // 'launch' | 'resume' | 'stop' | null
  const [confirmStop, setConfirmStop] = useState(false)
  const [showBroadcast, setShowBroadcast] = useState(false)
  const [broadcastText, setBroadcastText] = useState('')
  const [broadcasting, setBroadcasting] = useState(false)
  const [togglingAutoQueue, setTogglingAutoQueue] = useState(false)
  const toast = useToast()
  const { requestPermission } = useNotifications()

  const launchMutation = useLaunchSwarm()
  const stopMutation = useStopSwarm()
  const directiveMutation = useSendDirective()
  const updateConfigMutation = useUpdateProjectConfig()

  const autoQueueEnabled = config?.auto_queue ?? false

  const isLoading = loadingAction !== null

  const handleLaunch = async (resume = false) => {
    setLoadingAction(resume ? 'resume' : 'launch')
    // Non-blocking permission request on first launch
    requestPermission()
    try {
      await launchMutation.mutateAsync({
        project_id: projectId,
        resume,
        no_confirm: true,
        agent_count: config?.agent_count ?? 4,
        max_phases: config?.max_phases ?? 999,
      })
      toast(resume ? 'Swarm resumed' : 'Swarm launched', 'success')
      onAction?.()
    } catch (e) {
      toast(`Launch failed: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: () => handleLaunch(resume) })
    } finally {
      setLoadingAction(null)
    }
  }

  const handleStop = async () => {
    setConfirmStop(false)
    setLoadingAction('stop')
    try {
      await stopMutation.mutateAsync({ project_id: projectId })
      toast('Swarm stopped', 'success')
      onAction?.()
    } catch (e) {
      toast(`Stop failed: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: handleStop })
    } finally {
      setLoadingAction(null)
    }
  }

  const handleBroadcast = async () => {
    const text = broadcastText.trim()
    if (!text || !agents) return
    setBroadcasting(true)
    const aliveAgents = agents.filter(a => a.alive)
    try {
      await Promise.all(aliveAgents.map(a =>
        directiveMutation.mutateAsync({ projectId, agentName: a.name, text, priority: 'normal' })
      ))
      toast(`Directive sent to ${aliveAgents.length} agents`, 'success')
      setBroadcastText('')
      setShowBroadcast(false)
    } catch (e) {
      toast(`Broadcast failed: ${e.message}`, 'error')
    } finally {
      setBroadcasting(false)
    }
  }

  const handleToggleAutoQueue = async () => {
    setTogglingAutoQueue(true)
    const newValue = !autoQueueEnabled
    try {
      await updateConfigMutation.mutateAsync({
        projectId,
        config: {
          ...config,
          auto_queue: newValue,
          auto_queue_delay_seconds: config?.auto_queue_delay_seconds ?? 30,
        },
      })
      toast(newValue ? 'Auto-queue enabled' : 'Auto-queue disabled', 'success')
      onAction?.()
    } catch (e) {
      toast(`Failed to toggle auto-queue: ${e.message}`, 'error')
    } finally {
      setTogglingAutoQueue(false)
    }
  }

  const aliveCount = agents?.filter(a => a.alive).length ?? 0

  const Spinner = () => (
    <span className="inline-block w-3.5 h-3.5 border-2 border-current/30 border-t-current rounded-full animate-spin" aria-hidden="true" />
  )

  return (
    <>
      <div className="flex items-center gap-1.5 sm:gap-2">
        {status === 'running' ? (
          <>
            <button
              onClick={() => setConfirmStop(true)}
              disabled={isLoading}
              aria-busy={loadingAction === 'stop'}
              className="btn-neon btn-neon-danger px-3 sm:px-4 py-1.5 sm:py-2 rounded text-xs sm:text-sm disabled:opacity-50 flex items-center gap-1.5 sm:gap-2"
            >
              {loadingAction === 'stop' ? <><Spinner /> Stopping...</> : 'Stop Swarm'}
            </button>
            {aliveCount > 0 && (
              <button
                onClick={() => setShowBroadcast(!showBroadcast)}
                aria-expanded={showBroadcast}
                className={`px-3 sm:px-4 py-1.5 sm:py-2 rounded text-xs sm:text-sm font-mono cursor-pointer border transition-colors ${
                  showBroadcast
                    ? 'bg-crt-cyan/10 border-crt-cyan/30 text-crt-cyan'
                    : 'bg-transparent border-retro-border text-zinc-400 hover:text-crt-cyan hover:border-crt-cyan/30'
                }`}
                title="Send directive to all agents"
                aria-label="Direct all agents"
              >
                Direct All
              </button>
            )}
            {/* Auto-Queue Toggle (also visible when running) */}
            <button
              onClick={handleToggleAutoQueue}
              disabled={togglingAutoQueue}
              title={autoQueueEnabled ? 'Auto-queue ON: will auto-resume when agents finish' : 'Auto-queue OFF: click to enable'}
              className={`px-3 sm:px-4 py-1.5 sm:py-2 rounded text-xs sm:text-sm font-mono cursor-pointer border transition-all flex items-center gap-1.5 ${
                autoQueueEnabled
                  ? 'bg-crt-green/20 border-crt-green/50 text-crt-green hover:bg-crt-green/30'
                  : 'bg-transparent border-retro-border text-zinc-500 hover:text-zinc-300 hover:border-zinc-500'
              } ${togglingAutoQueue ? 'opacity-50' : ''}`}
              aria-pressed={autoQueueEnabled}
              aria-label={autoQueueEnabled ? 'Disable auto-queue' : 'Enable auto-queue'}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 2l4 4-4 4" />
                <path d="M3 11v-1a4 4 0 014-4h14" />
                <path d="M7 22l-4-4 4-4" />
                <path d="M21 13v1a4 4 0 01-4 4H3" />
              </svg>
              <span className="hidden sm:inline">{autoQueueEnabled ? 'Auto' : 'Auto'}</span>
            </button>
          </>
        ) : (
          <>
            <button
              onClick={() => handleLaunch(false)}
              disabled={isLoading}
              aria-busy={loadingAction === 'launch'}
              className="btn-neon px-3 sm:px-4 py-1.5 sm:py-2 rounded text-xs sm:text-sm disabled:opacity-50 flex items-center gap-1.5 sm:gap-2"
            >
              {loadingAction === 'launch' ? <><Spinner /> Launching...</> : 'Launch'}
            </button>
            {status === 'stopped' && (
              <button
                onClick={() => handleLaunch(true)}
                disabled={isLoading}
                aria-busy={loadingAction === 'resume'}
                className="px-3 sm:px-4 py-1.5 sm:py-2 rounded bg-retro-grid hover:bg-retro-border text-zinc-200 text-xs sm:text-sm font-medium transition-colors disabled:opacity-50 cursor-pointer border border-retro-border font-mono flex items-center gap-1.5 sm:gap-2"
              >
                {loadingAction === 'resume' ? <><Spinner /> Resuming...</> : 'Resume'}
              </button>
            )}
            {/* Auto-Queue Toggle */}
            <button
              onClick={handleToggleAutoQueue}
              disabled={togglingAutoQueue}
              title={autoQueueEnabled ? 'Auto-queue ON: will auto-resume when agents finish' : 'Auto-queue OFF: click to enable'}
              className={`px-3 sm:px-4 py-1.5 sm:py-2 rounded text-xs sm:text-sm font-mono cursor-pointer border transition-all flex items-center gap-1.5 ${
                autoQueueEnabled
                  ? 'bg-crt-green/20 border-crt-green/50 text-crt-green hover:bg-crt-green/30'
                  : 'bg-transparent border-retro-border text-zinc-500 hover:text-zinc-300 hover:border-zinc-500'
              } ${togglingAutoQueue ? 'opacity-50' : ''}`}
              aria-pressed={autoQueueEnabled}
              aria-label={autoQueueEnabled ? 'Disable auto-queue' : 'Enable auto-queue'}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M17 2l4 4-4 4" />
                <path d="M3 11v-1a4 4 0 014-4h14" />
                <path d="M7 22l-4-4 4-4" />
                <path d="M21 13v1a4 4 0 01-4 4H3" />
              </svg>
              <span className="hidden sm:inline">{autoQueueEnabled ? 'Auto' : 'Auto'}</span>
            </button>
          </>
        )}
      </div>

      {/* Broadcast directive panel */}
      {showBroadcast && (
        <div className="mt-2 retro-panel border border-retro-border rounded p-3 animate-fade-in">
          <div className="flex items-center justify-between mb-2">
            <span className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-mono">Direct All Agents</span>
            <button onClick={() => setShowBroadcast(false)} className="text-zinc-500 hover:text-zinc-300 bg-transparent border-0 cursor-pointer text-xs" aria-label="Close broadcast panel">✕</button>
          </div>
          <textarea
            value={broadcastText}
            onChange={(e) => setBroadcastText(e.target.value)}
            placeholder="Enter directive for all agents..."
            rows={2}
            maxLength={5000}
            className="retro-input w-full px-2 py-1.5 text-[11px] font-mono resize-none rounded mb-2"
            aria-label="Broadcast directive text"
            disabled={broadcasting}
            onKeyDown={(e) => { if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); handleBroadcast() } }}
          />
          <div className="flex items-center justify-between">
            <span className="text-[9px] text-zinc-700 font-mono">{aliveCount} agent{aliveCount !== 1 ? 's' : ''} will receive this</span>
            <button
              onClick={handleBroadcast}
              disabled={broadcasting || !broadcastText.trim()}
              className="btn-neon px-3 py-1 rounded text-[11px] disabled:opacity-30 flex items-center gap-1.5"
              aria-busy={broadcasting}
            >
              {broadcasting ? 'Sending...' : 'Send to All'}
            </button>
          </div>
        </div>
      )}

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
