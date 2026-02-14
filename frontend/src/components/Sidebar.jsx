import { useState, useRef, useCallback, useDeferredValue } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { deleteProject, archiveProject, unarchiveProject } from '../lib/api'
import ConfirmDialog from './ConfirmDialog'
import { useToast } from './Toast'

// Preload route chunks on hover (fires import once per route, cached by bundler)
let _projectViewPreloaded = false
function preloadProjectView() {
  if (_projectViewPreloaded) return
  _projectViewPreloaded = true
  import('./ProjectView').catch(() => { _projectViewPreloaded = false })
}

let _newProjectPreloaded = false
function preloadNewProject() {
  if (_newProjectPreloaded) return
  _newProjectPreloaded = true
  import('./NewProject').catch(() => { _newProjectPreloaded = false })
}

const ORDER_KEY = 'lu_project_order'

const statusColors = {
  running: 'bg-emerald-500',
  stopped: 'bg-zinc-500',
  created: 'bg-amber-500',
}

const statusGlow = {
  running: 'led-active',
  stopped: '',
  created: 'led-warning',
}

// Shape icons for color-independent status (WCAG 1.4.1)
function ProjectStatusIcon({ status }) {
  const size = 8
  switch (status) {
    case 'running':
      // Filled circle (running)
      return (
        <svg width={size} height={size} viewBox="0 0 8 8" className="shrink-0 text-emerald-500" aria-hidden="true">
          <circle cx="4" cy="4" r="3.5" fill="currentColor" />
        </svg>
      )
    case 'stopped':
      // Hollow circle (stopped)
      return (
        <svg width={size} height={size} viewBox="0 0 8 8" className="shrink-0 text-zinc-500" aria-hidden="true">
          <circle cx="4" cy="4" r="2.5" fill="none" stroke="currentColor" strokeWidth="1.5" />
        </svg>
      )
    case 'created':
      // Triangle (created/new)
      return (
        <svg width={size} height={size} viewBox="0 0 8 8" className="shrink-0 text-amber-500" aria-hidden="true">
          <path d="M4 1L7 7H1z" fill="currentColor" />
        </svg>
      )
    default:
      // Diamond (unknown)
      return (
        <svg width={size} height={size} viewBox="0 0 8 8" className="shrink-0 text-zinc-600" aria-hidden="true">
          <path d="M4 1L7 4L4 7L1 4z" fill="currentColor" />
        </svg>
      )
  }
}

const statusFilters = ['all', 'running', 'stopped', 'created']

function loadOrder() {
  try {
    const stored = localStorage.getItem(ORDER_KEY)
    return stored ? JSON.parse(stored) : []
  } catch {
    return []
  }
}

function saveOrder(order) {
  try {
    localStorage.setItem(ORDER_KEY, JSON.stringify(order))
  } catch {}
}

function sortByOrder(projects, order) {
  if (!order.length) return projects
  const indexMap = new Map(order.map((id, i) => [id, i]))
  return [...projects].sort((a, b) => {
    const ai = indexMap.has(a.id) ? indexMap.get(a.id) : Infinity
    const bi = indexMap.has(b.id) ? indexMap.get(b.id) : Infinity
    return ai - bi
  })
}

export default function Sidebar({ projects, onRefresh, collapsed, onToggle, showArchived, onShowArchivedChange, projectHealth }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const activeId = id ? Number(id) : null
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const debouncedSearch = useDeferredValue(search)

  // Drag-and-drop state
  const [customOrder, setCustomOrder] = useState(loadOrder)
  const dragItem = useRef(null)
  const dragOverItem = useRef(null)
  const [dragOverId, setDragOverId] = useState(null)

  const isFiltering = statusFilter !== 'all' || !!debouncedSearch
  const canDrag = !isFiltering

  const filteredProjects = projects.filter((p) => {
    if (statusFilter !== 'all' && p.status !== statusFilter) return false
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase()
      return (p.name || '').toLowerCase().includes(q) || (p.goal || '').toLowerCase().includes(q)
    }
    return true
  })

  // Apply custom order only when not filtering
  const orderedProjects = canDrag ? sortByOrder(filteredProjects, customOrder) : filteredProjects

  const handleDragStart = useCallback((e, projectId) => {
    dragItem.current = projectId
    e.dataTransfer.effectAllowed = 'move'
    // Make the drag image slightly transparent
    if (e.target) {
      e.target.style.opacity = '0.5'
    }
  }, [])

  const handleDragEnd = useCallback((e) => {
    if (e.target) {
      e.target.style.opacity = '1'
    }
    setDragOverId(null)

    if (dragItem.current != null && dragOverItem.current != null && dragItem.current !== dragOverItem.current) {
      // Compute new order from current ordered projects
      const currentIds = orderedProjects.map(p => p.id)
      const fromIdx = currentIds.indexOf(dragItem.current)
      const toIdx = currentIds.indexOf(dragOverItem.current)

      if (fromIdx !== -1 && toIdx !== -1) {
        const newOrder = [...currentIds]
        newOrder.splice(fromIdx, 1)
        newOrder.splice(toIdx, 0, dragItem.current)
        setCustomOrder(newOrder)
        saveOrder(newOrder)
      }
    }

    dragItem.current = null
    dragOverItem.current = null
  }, [orderedProjects])

  const handleDragOver = useCallback((e, projectId) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    dragOverItem.current = projectId
    setDragOverId(projectId)
  }, [])

  const handleDragLeave = useCallback(() => {
    setDragOverId(null)
  }, [])

  // Preload ProjectView chunk on hover for faster navigation
  const handleProjectHover = useCallback(() => {
    preloadProjectView()
  }, [])

  // Keyboard reorder: move a project up or down in the list
  const handleMoveProject = useCallback((projectId, direction) => {
    const currentIds = orderedProjects.map(p => p.id)
    const idx = currentIds.indexOf(projectId)
    if (idx === -1) return
    const targetIdx = direction === 'up' ? idx - 1 : idx + 1
    if (targetIdx < 0 || targetIdx >= currentIds.length) return
    const newOrder = [...currentIds]
    ;[newOrder[idx], newOrder[targetIdx]] = [newOrder[targetIdx], newOrder[idx]]
    setCustomOrder(newOrder)
    saveOrder(newOrder)
  }, [orderedProjects])

  return (
    <>
      {/* Mobile overlay */}
      {!collapsed && (
        <div
          className="fixed inset-0 bg-black/60 z-20 lg:hidden"
          onClick={onToggle}
          aria-hidden="true"
        />
      )}

      <aside className={`${collapsed ? 'w-0 -translate-x-full lg:w-0 lg:-translate-x-full' : 'w-64 translate-x-0'} fixed lg:relative z-30 h-full bg-retro-dark border-r border-retro-border flex flex-col transition-all duration-200 overflow-hidden shrink-0`}>
        {/* Header */}
        <div className="p-4 border-b border-retro-border flex items-center justify-between">
          <Link to="/" className="flex items-center gap-2 no-underline">
            <div className="w-8 h-8 rounded bg-crt-green/20 border border-crt-green/40 flex items-center justify-center neon-green font-bold text-sm shrink-0">
              LU
            </div>
            <div className="whitespace-nowrap">
              <div className="text-sm font-semibold text-zinc-100">Latent Underground</div>
              <div className="text-[10px] text-crt-green/60 tracking-[0.2em] uppercase font-mono">Swarm Control</div>
            </div>
          </Link>
          <button
            onClick={onToggle}
            className="p-1.5 rounded-md text-zinc-400 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer lg:hidden transition-colors"
            title="Close sidebar"
            aria-label="Close sidebar"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><path d="M12 4L4 12M4 4l8 8" /></svg>
          </button>
        </div>

        {/* New Project Button */}
        <div className="p-3">
          <button
            onClick={() => { navigate('/projects/new'); onToggle?.() }}
            onMouseEnter={preloadNewProject}
            onFocus={preloadNewProject}
            className="btn-neon w-full py-2 px-3 rounded text-sm whitespace-nowrap"
          >
            + New Project
          </button>
        </div>

        {/* Search + Filter */}
        <div className="px-3 pb-2 space-y-2">
          <input
            id="sidebar-search"
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search projects..."
            aria-label="Search projects"
            className="retro-input w-full px-2.5 py-1.5 text-xs"
          />
          <div className="flex gap-1 items-center">
            {statusFilters.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                aria-pressed={statusFilter === s}
                aria-label={`Filter by ${s} status`}
                className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors cursor-pointer border-0 font-mono capitalize ${
                  statusFilter === s ? 'bg-retro-grid text-crt-green border border-crt-green/30' : 'text-zinc-500 hover:text-zinc-300 bg-transparent'
                }`}
              >
                {s === 'all' ? 'All' : s}
              </button>
            ))}
            <label className="flex items-center gap-1 ml-auto cursor-pointer select-none" title="Show archived projects">
              <input
                type="checkbox"
                checked={showArchived}
                onChange={(e) => onShowArchivedChange?.(e.target.checked)}
                className="accent-crt-green w-3 h-3 cursor-pointer"
              />
              <span className="text-[10px] text-zinc-500 font-mono">Archived</span>
            </label>
          </div>
        </div>

        {/* Project List */}
        <div className="flex-1 overflow-y-auto px-2">
          <div className="px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-medium font-mono flex items-center justify-between">
            <span>Projects</span>
            {canDrag && projects.length > 1 && (
              <span className="text-[9px] text-zinc-700 normal-case tracking-normal">drag to reorder</span>
            )}
          </div>
          {projects.length === 0 && (
            <div className="px-3 py-4 text-sm text-zinc-600 text-center">
              No projects yet
            </div>
          )}
          {filteredProjects.length === 0 && projects.length > 0 && (
            <div className="px-3 py-4 text-sm text-zinc-600 text-center">
              No matching projects
            </div>
          )}
          {orderedProjects.map((p) => {
            const isArchived = !!p.archived_at
            const isDragOver = dragOverId === p.id && dragItem.current !== p.id
            return (
            <div
              key={p.id}
              className={`group relative mb-0.5 ${isArchived ? 'opacity-50' : ''} ${isDragOver ? 'border-t-2 border-crt-green' : 'border-t-2 border-transparent'}`}
              draggable={canDrag}
              onDragStart={(e) => handleDragStart(e, p.id)}
              onDragEnd={handleDragEnd}
              onDragOver={(e) => handleDragOver(e, p.id)}
              onDragLeave={handleDragLeave}
            >
              <div className="flex items-center">
                {canDrag && (
                  <div className="shrink-0 flex flex-col items-center gap-0">
                    <div
                      className="w-4 flex items-center justify-center cursor-grab opacity-0 group-hover:opacity-60 transition-opacity text-zinc-600"
                      aria-hidden="true"
                    >
                      <svg width="8" height="12" viewBox="0 0 8 12" fill="currentColor">
                        <circle cx="2" cy="2" r="1" />
                        <circle cx="6" cy="2" r="1" />
                        <circle cx="2" cy="6" r="1" />
                        <circle cx="6" cy="6" r="1" />
                        <circle cx="2" cy="10" r="1" />
                        <circle cx="6" cy="10" r="1" />
                      </svg>
                    </div>
                    <div className="flex flex-col opacity-0 focus-within:opacity-100 transition-opacity">
                      <button
                        onClick={() => handleMoveProject(p.id, 'up')}
                        disabled={orderedProjects.indexOf(p) === 0}
                        className="w-4 h-4 flex items-center justify-center text-zinc-600 hover:text-crt-green focus:text-crt-green bg-transparent border-0 cursor-pointer disabled:opacity-30 disabled:cursor-default p-0 focus:outline-none focus:ring-1 focus:ring-crt-green rounded"
                        aria-label={`Move ${p.name} up`}
                        title="Move up"
                      >
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M1 5l3-3 3 3" /></svg>
                      </button>
                      <button
                        onClick={() => handleMoveProject(p.id, 'down')}
                        disabled={orderedProjects.indexOf(p) === orderedProjects.length - 1}
                        className="w-4 h-4 flex items-center justify-center text-zinc-600 hover:text-crt-green focus:text-crt-green bg-transparent border-0 cursor-pointer disabled:opacity-30 disabled:cursor-default p-0 focus:outline-none focus:ring-1 focus:ring-crt-green rounded"
                        aria-label={`Move ${p.name} down`}
                        title="Move down"
                      >
                        <svg width="8" height="8" viewBox="0 0 8 8" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><path d="M1 3l3 3 3-3" /></svg>
                      </button>
                    </div>
                  </div>
                )}
                <Link
                  to={`/projects/${p.id}`}
                  onMouseEnter={handleProjectHover}
                  onFocus={handleProjectHover}
                  className={`block flex-1 px-3 py-2 ${canDrag ? 'pr-14' : 'pr-14'} rounded no-underline transition-colors ${
                    activeId === p.id
                      ? 'bg-retro-grid text-zinc-100 border-l-2 border-crt-green'
                      : 'text-zinc-400 hover:bg-retro-grid/50 hover:text-zinc-200'
                  }`}
                >
                  <div className="flex items-center gap-2">
                    <ProjectStatusIcon status={p.status} />
                    <span className="sr-only">{`Status: ${p.status || 'unknown'}`}</span>
                    <span className="text-sm truncate font-mono">{p.name}</span>
                    {projectHealth?.[p.id] && projectHealth[p.id] !== 'gray' && (
                      <span className="relative group/health inline-flex items-center gap-0.5 shrink-0">
                        {projectHealth[p.id] === 'green' ? (
                          <svg width="7" height="7" viewBox="0 0 7 7" aria-hidden="true" className="text-crt-green">
                            <circle cx="3.5" cy="3.5" r="3" fill="currentColor" />
                          </svg>
                        ) : projectHealth[p.id] === 'yellow' ? (
                          <svg width="7" height="7" viewBox="0 0 7 7" aria-hidden="true" className="text-signal-amber">
                            <path d="M3.5 0.5L6.5 6H0.5z" fill="currentColor" />
                          </svg>
                        ) : (
                          <svg width="7" height="7" viewBox="0 0 7 7" aria-hidden="true" className="text-signal-red">
                            <path d="M3.5 0.5L6.5 3.5L3.5 6.5L0.5 3.5z" fill="currentColor" />
                          </svg>
                        )}
                        <span className="sr-only">{`Health: ${
                          projectHealth[p.id] === 'green' ? 'Healthy' :
                          projectHealth[p.id] === 'yellow' ? 'Warning' : 'Critical'
                        }`}</span>
                        <span className="hidden group-hover/health:block absolute left-full ml-1 bg-retro-dark border border-retro-border rounded px-1.5 py-0.5 text-[9px] font-mono text-zinc-400 whitespace-nowrap z-50 shadow-lg">
                          {projectHealth[p.id] === 'green' ? 'Healthy' :
                           projectHealth[p.id] === 'yellow' ? 'Warning' : 'Critical'}
                        </span>
                      </span>
                    )}
                    {isArchived && (
                      <span className="text-[8px] font-mono uppercase tracking-wider text-crt-amber/70 bg-crt-amber/10 px-1 py-0.5 rounded shrink-0">Archived</span>
                    )}
                  </div>
                  <div className={`${canDrag ? 'ml-4' : 'ml-4'} text-[11px] text-zinc-600 truncate`}>{p.goal}</div>
                </Link>
              </div>
              <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 focus-within:opacity-100 transition-opacity">
                <button
                  onClick={async (e) => {
                    e.preventDefault(); e.stopPropagation()
                    try {
                      if (isArchived) {
                        await unarchiveProject(p.id)
                        toast('Project unarchived', 'success')
                      } else {
                        await archiveProject(p.id)
                        toast('Project archived', 'success')
                      }
                      onRefresh?.()
                    } catch (err) {
                      toast(`${isArchived ? 'Unarchive' : 'Archive'} failed: ${err.message}`, 'error')
                    }
                  }}
                  className="p-2 rounded text-zinc-600 hover:text-crt-amber hover:bg-retro-grid focus:text-crt-amber focus:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors focus:outline-none focus:ring-1 focus:ring-crt-amber min-w-[32px] min-h-[32px] flex items-center justify-center"
                  aria-label={`${isArchived ? 'Unarchive' : 'Archive'} ${p.name}`}
                  title={`${isArchived ? 'Unarchive' : 'Archive'} ${p.name}`}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1.5 3.5h13v3h-13z" />
                    <path d="M2.5 6.5v7h11v-7" />
                    <path d="M6 9h4" />
                  </svg>
                </button>
                <button
                  onClick={(e) => { e.preventDefault(); e.stopPropagation(); setDeleteTarget(p) }}
                  className="p-2 rounded text-zinc-600 hover:text-signal-red hover:bg-retro-grid focus:text-signal-red focus:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors focus:outline-none focus:ring-1 focus:ring-signal-red min-w-[32px] min-h-[32px] flex items-center justify-center"
                  aria-label={`Delete ${p.name}`}
                  title={`Delete ${p.name}`}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <path d="M2 4h12M5.33 4V2.67a1.33 1.33 0 011.34-1.34h2.66a1.33 1.33 0 011.34 1.34V4" />
                    <path d="M3.33 4l.67 9.33a1.33 1.33 0 001.33 1.34h5.34a1.33 1.33 0 001.33-1.34L12.67 4" />
                  </svg>
                </button>
              </div>
            </div>
            )
          })}
        </div>

        {/* Footer */}
        <div className="p-3 border-t border-retro-border text-[10px] text-zinc-600 text-center whitespace-nowrap font-mono">
          Latent Underground v{typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '0.1'}
        </div>
      </aside>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Project"
        message={deleteTarget ? `Delete "${deleteTarget.name}"? This removes the project record but does not delete any files on disk.` : ''}
        confirmLabel="Delete"
        danger
        onConfirm={async () => {
          const targetId = deleteTarget.id
          setDeleteTarget(null)
          try {
            await deleteProject(targetId)
            toast('Project deleted', 'success')
            onRefresh?.()
            if (activeId === targetId) navigate('/')
          } catch (e) {
            toast(`Delete failed: ${e.message}`, 'error', 4000, {
              label: 'Retry',
              onClick: () => deleteProject(targetId).then(() => { toast('Project deleted', 'success'); onRefresh?.() }).catch((e2) => toast(`Delete failed: ${e2.message}`, 'error'))
            })
          }
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </>
  )
}
