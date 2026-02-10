import { useState, useEffect, useCallback, useRef, memo } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { getSwarmStatus, getProject, deleteProject, archiveProject, unarchiveProject, startWatch, getProjectStats, getSwarmHistory } from '../lib/api'
import SwarmControls from './SwarmControls'
import AgentGrid from './AgentGrid'
import SignalPanel from './SignalPanel'
import TaskProgress from './TaskProgress'
import ActivityFeed from './ActivityFeed'
import { DashboardSkeleton } from './Skeleton'
import Sparkline from './Sparkline'
import ConfirmDialog from './ConfirmDialog'
import { useToast } from './Toast'

export default memo(function Dashboard({ wsEvents, onProjectChange }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const projectId = Number(id)
  const [project, setProject] = useState(null)
  const [status, setStatus] = useState(null)
  const [error, setError] = useState(null)
  const [stats, setStats] = useState(null)
  const [runs, setRuns] = useState([])
  const [confirmDelete, setConfirmDelete] = useState(false)
  const toast = useToast()
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const [proj, st, statsData, historyData] = await Promise.all([
        getProject(projectId),
        getSwarmStatus(projectId).catch(() => null),
        getProjectStats(projectId).catch(() => null),
        getSwarmHistory(projectId).catch(() => ({ runs: [] })),
      ])
      if (!mountedRef.current) return
      setProject(proj)
      setStatus(st)
      setStats(statsData)
      setRuns(historyData.runs || [])
      setError(null)
    } catch (e) {
      if (!mountedRef.current) return
      setError(e.message)
      toast(e.message, 'error', 4000, { label: 'Retry', onClick: refresh })
    }
  }, [projectId, toast])

  const intervalRef = useRef(null)

  useEffect(() => {
    refresh()
    startWatch(projectId).catch(() => {})

    const startPolling = () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
      intervalRef.current = setInterval(refresh, 10000)
    }

    const stopPolling = () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current)
        intervalRef.current = null
      }
    }

    const handleVisibility = () => {
      if (document.hidden) {
        stopPolling()
      } else {
        refresh()
        startPolling()
      }
    }

    if (!document.hidden) startPolling()
    document.addEventListener('visibilitychange', handleVisibility)

    return () => {
      stopPolling()
      document.removeEventListener('visibilitychange', handleVisibility)
    }
  }, [projectId, refresh])

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
    return () => {
      if (wsDebounceRef.current) clearTimeout(wsDebounceRef.current)
    }
  }, [wsEvents, refresh])

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

  if (error && !project) {
    return (
      <div className="flex-1 flex items-center justify-center p-8">
        <div className="retro-panel border border-retro-border rounded p-6 text-center max-w-sm">
          <div className="text-signal-red text-sm font-mono mb-3">{error}</div>
          <button
            onClick={refresh}
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

  return (
    <div className="flex-1 overflow-y-auto">
      {/* Header */}
      <div className="px-4 sm:px-6 py-4 border-b border-retro-border flex flex-col sm:flex-row sm:items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold text-zinc-100 m-0 font-mono">{project.name}</h1>
          <p className="text-sm text-zinc-500 mt-1 m-0">{project.goal}</p>
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
        <div className="flex items-center gap-2">
          <SwarmControls
            projectId={projectId}
            status={project.status}
            onAction={() => { refresh(); onProjectChange?.() }}
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
      <div className="p-4 sm:p-6 grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Task Progress */}
        <div className="col-span-full">
          <TaskProgress tasks={status?.tasks} />
        </div>

        {/* Agents */}
        <div>
          <AgentGrid agents={status?.agents} />
        </div>

        {/* Signals */}
        <div>
          <SignalPanel signals={status?.signals} phase={status?.phase} />
        </div>

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
