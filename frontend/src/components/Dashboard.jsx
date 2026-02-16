import { useState, useEffect, useCallback, useRef, memo, lazy, Suspense } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQueryClient } from '@tanstack/react-query'
import { getSwarmHistory, deleteProject, archiveProject, unarchiveProject, startWatch, createAbortable } from '../lib/api'
import { useProject, useProjectStats, useProjectGuardrails, projectKeys } from '../hooks/useProjectQuery'
import { useSwarmStatus, useSwarmHistory, useSwarmAgents, swarmKeys } from '../hooks/useSwarmQuery'
import SwarmControls from './SwarmControls'
import AgentGrid from './AgentGrid'
import SignalPanel from './SignalPanel'
import TaskProgress from './TaskProgress'
import ActivityFeed from './ActivityFeed'
import MessageBusPanel from './MessageBusPanel'
import { DashboardSkeleton } from './Skeleton'
import Sparkline from './Sparkline'
import RunSummary from './RunSummary'
import ConfirmDialog from './ConfirmDialog'
import { useToast } from './Toast'
import { useNotifications } from '../hooks/useNotifications'

// Lazy-load heavy dashboard components for bundle splitting
const AgentTimeline = lazy(() => import('./AgentTimeline'))
const AgentEventLog = lazy(() => import('./AgentEventLog'))
const ProjectStatusTimeline = lazy(() => import('./ProjectStatusTimeline'))
const ProjectHealthCard = lazy(() => import('./ProjectHealthCard'))
const CheckpointTimeline = lazy(() => import('./CheckpointTimeline'))

export default memo(function Dashboard({ wsEvents, onProjectChange }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const projectId = Number(id)
  const [confirmDelete, setConfirmDelete] = useState(false)
  const toast = useToast()
  const { notify } = useNotifications()
  const prevAgentsRef = useRef(null)

  // TanStack Query hooks replace manual useState + useEffect fetch patterns
  const { data: project, error: projectError, refetch: refetchProject } = useProject(projectId, {
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  })

  const { data: status } = useSwarmStatus(projectId, {
    refetchInterval: 10_000,
    refetchIntervalInBackground: false,
  })

  const { data: stats } = useProjectStats(projectId, {
    refetchInterval: 30_000,
  })

  const { data: historyData } = useSwarmHistory(projectId, {
    refetchInterval: 30_000,
  })

  const { data: agentsData } = useSwarmAgents(projectId, {
    refetchInterval: 5_000,
    refetchIntervalInBackground: false,
  })

  const { data: guardrailData } = useProjectGuardrails(projectId, {
    refetchInterval: 30_000,
  })

  const runs = historyData?.runs || []
  const processAgents = agentsData?.agents || null

  // Refresh all queries
  const refresh = useCallback(() => {
    queryClient.invalidateQueries({ queryKey: projectKeys.detail(projectId) })
    queryClient.invalidateQueries({ queryKey: swarmKeys.status(projectId) })
    queryClient.invalidateQueries({ queryKey: swarmKeys.agents(projectId) })
    queryClient.invalidateQueries({ queryKey: swarmKeys.history(projectId) })
    queryClient.invalidateQueries({ queryKey: projectKeys.stats(projectId) })
  }, [queryClient, projectId])

  // Start watching on mount
  useEffect(() => {
    startWatch(projectId).catch(() => {})
  }, [projectId])

  // Detect agent state transitions and fire browser notifications
  useEffect(() => {
    if (!processAgents || !project) return
    const prev = prevAgentsRef.current
    prevAgentsRef.current = processAgents

    if (!prev || prev.length === 0) return

    const prevAlive = new Set(prev.filter(a => a.alive).map(a => a.name))
    if (prevAlive.size === 0) return

    const crashed = processAgents.filter(a =>
      !a.alive && a.exit_code != null && a.exit_code !== 0 && prevAlive.has(a.name)
    )

    for (const a of crashed) {
      notify(`${a.name} crashed`, {
        body: `${project.name}: ${a.name} exited with code ${a.exit_code}`,
        tag: `agent-crash-${projectId}-${a.name}`,
      })
    }

    const nowAlive = processAgents.filter(a => a.alive).length
    if (nowAlive === 0 && prevAlive.size > 0 && crashed.length === 0) {
      notify('Swarm completed', {
        body: `${project.name}: All agents finished successfully.`,
        tag: `swarm-complete-${projectId}`,
      })
    } else if (nowAlive === 0 && prevAlive.size > 0 && crashed.length > 0) {
      notify('Swarm finished with errors', {
        body: `${project.name}: ${crashed.length} agent${crashed.length !== 1 ? 's' : ''} crashed.`,
        tag: `swarm-complete-${projectId}`,
      })
    }
  }, [processAgents, project, projectId, notify])

  // Debounced refresh on WebSocket events (coalesce rapid heartbeats)
  const wsDebounceRef = useRef(null)
  useEffect(() => {
    if (!wsEvents) return
    const ev = wsEvents
    if (ev.type === 'heartbeat' || ev.type === 'signal' || ev.type === 'tasks') {
      if (wsDebounceRef.current) clearTimeout(wsDebounceRef.current)
      wsDebounceRef.current = setTimeout(() => {
        refresh()
        wsDebounceRef.current = null
      }, 1000)
    }
    // Handle circuit breaker events
    if (ev.type === 'circuit_breaker_opened') {
      toast(`Circuit breaker opened for ${ev.agent}: too many failures`, 'error', 6000)
    }
    if (ev.type === 'circuit_breaker_closed') {
      toast(`Circuit breaker closed for ${ev.agent}: recovered`, 'success', 4000)
    }
    return () => {
      if (wsDebounceRef.current) clearTimeout(wsDebounceRef.current)
    }
  }, [wsEvents, refresh, toast])

  const handleExport = async () => {
    try {
      const history = await getSwarmHistory(projectId).catch(() => ({ runs: [] }))
      const exportData = {
        project: { ...project, config: project.config ? JSON.parse(project.config) : null },
        stats: stats || null,
        history: history.runs || [],
        exported_at: new Date().toISOString(),
      }
      const blob = new Blob([JSON.stringify(exportData, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${project.name.replace(/[^a-zA-Z0-9-_]/g, '_')}-export.json`
      a.click()
      URL.revokeObjectURL(url)
      toast('Project exported', 'success')
    } catch (e) {
      toast(`Export failed: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: handleExport })
    }
  }

  const handleDelete = async () => {
    setConfirmDelete(false)
    try {
      await deleteProject(projectId)
      toast('Project deleted', 'success')
      queryClient.invalidateQueries({ queryKey: projectKeys.lists() })
      onProjectChange?.()
      navigate('/')
    } catch (e) {
      toast(`Delete failed: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: handleDelete })
    }
  }

  const handleArchiveToggle = async () => {
    const isArchived = !!project.archived_at
    try {
      if (isArchived) {
        await unarchiveProject(projectId)
        toast('Project unarchived', 'success')
      } else {
        await archiveProject(projectId)
        toast('Project archived', 'success')
      }
      refresh()
      onProjectChange?.()
    } catch (e) {
      toast(`${isArchived ? 'Unarchive' : 'Archive'} failed: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: handleArchiveToggle })
    }
  }

  const error = projectError?.message

  if (error && !project) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="retro-panel border border-retro-border rounded p-6 text-center max-w-sm">
          <div className="text-signal-red text-sm font-mono mb-3 flex items-center justify-center gap-2" role="alert">
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" className="shrink-0" aria-hidden="true">
              <circle cx="8" cy="8" r="7" stroke="currentColor" strokeWidth="1.5" />
              <path d="M8 4v5M8 11v1" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
            </svg>
            <span>{error}</span>
          </div>
          <button
            onClick={() => refetchProject()}
            className="btn-neon px-4 py-2 rounded text-sm"
          >
            Retry
          </button>
        </div>
      </div>
    )
  }

  if (!project) {
    return <DashboardSkeleton />
  }

  const parsedConfig = (() => {
    if (!project.config) return null
    try { return JSON.parse(project.config) } catch { return null }
  })()

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="px-3 sm:px-4 md:px-6 py-3 sm:py-4 border-b border-retro-border flex flex-col sm:flex-row sm:items-center justify-between gap-2 sm:gap-3">
        <div className="min-w-0">
          <h1 className="text-lg sm:text-xl font-semibold text-zinc-100 m-0 font-mono truncate">{project.name}</h1>
          <p className="text-xs sm:text-sm text-zinc-500 mt-1 m-0 line-clamp-2">{project.goal}</p>
          {stats && stats.total_runs > 0 && (
            <div className="flex items-center gap-3 mt-1 text-xs text-zinc-600 font-mono flex-wrap">
              <span>{stats.total_runs} run{stats.total_runs !== 1 ? 's' : ''}</span>
              {stats.avg_duration_seconds != null && (
                <span>avg {Math.round(stats.avg_duration_seconds / 60)}m</span>
              )}
              <span>{stats.total_tasks_completed} tasks completed</span>
              {runs.length > 1 && (
                <span className="hidden sm:contents">
                  <span className="text-zinc-600" title="Task completion trend">tasks</span>
                  <Sparkline data={runs.map(r => r.tasks_completed || 0)} />
                  <span className="text-zinc-600" title="Run duration trend">duration</span>
                  <Sparkline data={runs.map(r => r.duration_seconds || 0)} color="#E87838" />
                </span>
              )}
            </div>
          )}
        </div>
        <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
          <SwarmControls
            projectId={projectId}
            status={project.status}
            config={parsedConfig}
            onAction={() => { refresh(); onProjectChange?.() }}
            agents={processAgents}
          />
          <button
            onClick={handleExport}
            className="p-2 rounded text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
            title="Export project"
            aria-label="Export project"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M8 2v8M5 7l3 3 3-3M3 12v1.5h10V12" />
            </svg>
          </button>
          <button
            onClick={handleArchiveToggle}
            className="p-2 rounded text-zinc-500 hover:text-crt-amber hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
            title={project.archived_at ? 'Unarchive project' : 'Archive project'}
            aria-label={project.archived_at ? 'Unarchive project' : 'Archive project'}
          >
            {project.archived_at ? (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1.5 3.5h13v3h-13z" />
                <path d="M2.5 6.5v7h11v-7" />
                <path d="M6.5 10l1.5-1.5L9.5 10" />
              </svg>
            ) : (
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M1.5 3.5h13v3h-13z" />
                <path d="M2.5 6.5v7h11v-7" />
                <path d="M6 9h4" />
              </svg>
            )}
          </button>
          <button
            onClick={() => setConfirmDelete(true)}
            className="p-2 rounded text-zinc-500 hover:text-signal-red hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
            title="Delete project"
            aria-label="Delete project"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
              <path d="M2 4h12M5.33 4V2.67a1.33 1.33 0 011.34-1.34h2.66a1.33 1.33 0 011.34 1.34V4M6.67 7.33v4M9.33 7.33v4" />
              <path d="M3.33 4l.67 9.33a1.33 1.33 0 001.33 1.34h5.34a1.33 1.33 0 001.33-1.34L12.67 4" />
            </svg>
          </button>
        </div>
      </div>

      {/* Dashboard Grid */}
      <div className="p-3 sm:p-4 md:p-6 grid grid-cols-1 md:grid-cols-2 gap-3 sm:gap-4">
        {/* Task Progress */}
        <div className="col-span-full">
          <TaskProgress tasks={status?.tasks} />
        </div>

        {/* Agents */}
        <div>
          <AgentGrid agents={status?.agents} processAgents={processAgents} projectId={projectId} />
        </div>

        {/* Signals */}
        <div>
          <SignalPanel signals={status?.signals} phase={status?.phase} />
        </div>

        {/* Message Bus */}
        <div className="col-span-full">
          <MessageBusPanel projectId={projectId} wsEvents={wsEvents} />
        </div>

        {/* Agent Timeline */}
        {processAgents && processAgents.length > 0 && (
          <div className="col-span-full">
            <Suspense fallback={<div className="retro-panel p-3 text-center text-zinc-500 font-mono text-xs animate-pulse" role="status">Loading timeline...</div>}>
              <AgentTimeline agents={processAgents} />
            </Suspense>
          </div>
        )}

        {/* Run Summary (shown when swarm is not running and agents have stopped) */}
        {processAgents && processAgents.length > 0 && !processAgents.some(a => a.alive) && runs.length > 0 && (
          <div className="col-span-full">
            <RunSummary run={runs[0]} agents={processAgents} />
          </div>
        )}

        {/* Guardrail Results (shown when last run has guardrail validation results) */}
        {guardrailData?.last_results && guardrailData.last_results.length > 0 && (
          <div className="col-span-full">
            <div className="retro-panel rounded p-4">
              <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">
                Guardrail Results
                {guardrailData.last_run_id && <span className="text-zinc-600 ml-2">(Run #{guardrailData.last_run_id})</span>}
              </h3>
              <div className="space-y-1.5">
                {guardrailData.last_results.map((result, i) => {
                  const passed = result.passed
                  const isHalt = result.action === 'halt'
                  return (
                    <div
                      key={i}
                      className={`flex items-center gap-2 px-2.5 py-1.5 rounded text-xs font-mono ${
                        passed
                          ? 'bg-crt-green/5 text-crt-green'
                          : isHalt
                            ? 'bg-signal-red/10 text-signal-red'
                            : 'bg-signal-amber/10 text-signal-amber'
                      }`}
                      data-testid={`guardrail-result-${i}`}
                    >
                      {/* Pass/fail icon */}
                      {passed ? (
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                          <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
                          <path d="M3.5 6l2 2 3-3.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" strokeLinejoin="round" />
                        </svg>
                      ) : (
                        <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
                          <circle cx="6" cy="6" r="5" stroke="currentColor" strokeWidth="1.2" />
                          <path d="M4 4l4 4M8 4l-4 4" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
                        </svg>
                      )}
                      <span className="font-medium">{result.rule_type}</span>
                      {result.pattern && <span className="text-zinc-500 truncate max-w-[150px]" title={result.pattern}>/{result.pattern}/</span>}
                      {result.threshold != null && <span className="text-zinc-500">({result.threshold})</span>}
                      <span className={`ml-auto text-[10px] px-1.5 py-0.5 rounded ${
                        isHalt ? 'bg-signal-red/15' : 'bg-signal-amber/15'
                      }`}>
                        {result.action}
                      </span>
                      {result.detail && <span className="text-zinc-500 text-[10px] hidden sm:inline">{result.detail}</span>}
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        )}

        {/* Project Health */}
        {runs.length > 0 && (
          <div className="col-span-full">
            <Suspense fallback={<div className="retro-panel p-3 text-center text-zinc-500 font-mono text-xs animate-pulse" role="status">Loading health...</div>}>
              <ProjectHealthCard projectId={projectId} />
            </Suspense>
          </div>
        )}

        {/* Agent Checkpoints (shown when a run exists) */}
        {runs.length > 0 && runs[0].id && (
          <div className="col-span-full">
            <Suspense fallback={<div className="retro-panel p-3 text-center text-zinc-500 font-mono text-xs animate-pulse" role="status">Loading checkpoints...</div>}>
              <CheckpointTimeline runId={runs[0].id} agents={processAgents} />
            </Suspense>
          </div>
        )}

        {/* Agent Event Log */}
        <div className="col-span-full">
          <Suspense fallback={<div className="retro-panel p-3 text-center text-zinc-500 font-mono text-xs animate-pulse" role="status">Loading events...</div>}>
            <AgentEventLog projectId={projectId} wsEvents={wsEvents} />
          </Suspense>
        </div>

        {/* Run History Timeline */}
        {runs.length > 0 && (
          <div className="col-span-full">
            <Suspense fallback={<div className="retro-panel p-3 text-center text-zinc-500 font-mono text-xs animate-pulse" role="status">Loading history...</div>}>
              <ProjectStatusTimeline runs={runs} />
            </Suspense>
          </div>
        )}

        {/* Activity */}
        <div className="col-span-full">
          <ActivityFeed projectId={projectId} wsEvents={wsEvents} />
        </div>
      </div>

      <ConfirmDialog
        open={confirmDelete}
        title="Delete Project"
        message={`Delete "${project.name}"? This removes the project record but does not delete any files on disk.`}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setConfirmDelete(false)}
      />
    </div>
  )
})
