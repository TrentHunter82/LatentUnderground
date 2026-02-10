import { useState } from 'react'
import { Link, useParams, useNavigate } from 'react-router-dom'
import { deleteProject, archiveProject, unarchiveProject } from '../lib/api'
import ConfirmDialog from './ConfirmDialog'
import { useToast } from './Toast'
import { useDebounce } from '../hooks/useDebounce'

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

const statusFilters = ['all', 'running', 'stopped', 'created']

export default function Sidebar({ projects, onRefresh, collapsed, onToggle, showArchived, onShowArchivedChange }) {
  const { id } = useParams()
  const navigate = useNavigate()
  const toast = useToast()
  const activeId = id ? Number(id) : null
  const [deleteTarget, setDeleteTarget] = useState(null)
  const [search, setSearch] = useState('')
  const [statusFilter, setStatusFilter] = useState('all')
  const debouncedSearch = useDebounce(search, 300)

  const filteredProjects = projects.filter((p) => {
    if (statusFilter !== 'all' && p.status !== statusFilter) return false
    if (debouncedSearch) {
      const q = debouncedSearch.toLowerCase()
      return (p.name || '').toLowerCase().includes(q) || (p.goal || '').toLowerCase().includes(q)
    }
    return true
  })

  return (
    <>
      {/* Mobile overlay */}
      {!collapsed && (
        <div
          className="fixed inset-0 bg-black/60 z-20 lg:hidden"
          onClick={onToggle}
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
          <div className="px-2 py-1 text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-medium font-mono">
            Projects
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
          {filteredProjects.map((p) => {
            const isArchived = !!p.archived_at
            return (
            <div key={p.id} className={`group relative mb-0.5 ${isArchived ? 'opacity-50' : ''}`}>
              <Link
                to={`/projects/${p.id}`}
                className={`block px-3 py-2 pr-14 rounded no-underline transition-colors ${
                  activeId === p.id
                    ? 'bg-retro-grid text-zinc-100 border-l-2 border-crt-green'
                    : 'text-zinc-400 hover:bg-retro-grid/50 hover:text-zinc-200'
                }`}
              >
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full shrink-0 ${statusColors[p.status] || 'bg-zinc-600'} ${statusGlow[p.status] || ''}`} aria-label={`Status: ${p.status || 'unknown'}`} />
                  <span className="text-sm truncate font-mono">{p.name}</span>
                  {isArchived && (
                    <span className="text-[8px] font-mono uppercase tracking-wider text-crt-amber/70 bg-crt-amber/10 px-1 py-0.5 rounded shrink-0">Archived</span>
                  )}
                </div>
                <div className="ml-4 text-[11px] text-zinc-600 truncate">{p.goal}</div>
              </Link>
              <div className="absolute right-1.5 top-1/2 -translate-y-1/2 flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
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
                  className="p-1 rounded text-zinc-600 hover:text-crt-amber hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
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
                  className="p-1 rounded text-zinc-600 hover:text-signal-red hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
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
