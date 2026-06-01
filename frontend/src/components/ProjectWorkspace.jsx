import {
  createContext, useContext, useCallback, useMemo, useRef, useState, useEffect,
  lazy, Suspense,
} from 'react'
import { DockviewReact } from 'dockview-react'
import 'dockview-react/dist/styles/dockview.css'
import './workspace.css'

import Dashboard from './Dashboard'
import TerminalOutput from './TerminalOutput'
import ProjectSettings from './ProjectSettings'
import WebhookManager from './WebhookManager'
import Sidebar from './Sidebar'
import { getSwarmHistory, getSwarmOutput, updateProjectConfig } from '../lib/api'
import { useAppChrome } from '../hooks/useAppChrome'

const LogViewer = lazy(() => import('./LogViewer'))
const SwarmHistory = lazy(() => import('./SwarmHistory'))
const FileEditor = lazy(() => import('./FileEditor'))
const Analytics = lazy(() => import('./Analytics'))

/* Project data flows to docked tiles via context (not dockview params) so the
   panels always see fresh wsEvents / project status without re-creating tiles. */
const WorkspaceContext = createContext(null)
function useWorkspace() {
  return useContext(WorkspaceContext)
}

const PANELS = [
  { id: 'navigator', title: 'Navigator' },
  { id: 'dashboard', title: 'Dashboard' },
  { id: 'output', title: 'Terminal' },
  { id: 'logs', title: 'Logs' },
  { id: 'history', title: 'History' },
  { id: 'files', title: 'Files' },
  { id: 'analytics', title: 'Analytics' },
  { id: 'settings', title: 'Settings' },
]

function PanelLoading({ label }) {
  return (
    <div className="p-6 text-center text-zinc-500 font-mono text-sm animate-pulse" role="status">
      Loading {label}…
    </div>
  )
}

/* ── Tile components ──────────────────────────────────────────────────────
   Stable module-level components; each reads live state from context. React
   context propagates through dockview's portals, so this is safe. */

function NavigatorPanel() {
  const chrome = useAppChrome() || {}
  return (
    <div className="lu-dock-panel lu-dock-navigator">
      <Sidebar
        projects={chrome.projects || []}
        onRefresh={chrome.onRefresh}
        collapsed={false}
        onToggle={() => {}}
        showArchived={!!chrome.showArchived}
        onShowArchivedChange={chrome.onShowArchivedChange}
        projectHealth={chrome.projectHealth}
      />
    </div>
  )
}

function DashboardPanel() {
  const { wsEvents, onProjectChange } = useWorkspace()
  return (
    <div className="lu-dock-panel">
      <div className="flex-1 min-h-0 overflow-y-auto">
        <Dashboard wsEvents={wsEvents} onProjectChange={onProjectChange} />
      </div>
    </div>
  )
}

function OutputPanel() {
  const { projectId, project } = useWorkspace()
  return (
    <div className="lu-dock-panel">
      <div className="flex-1 min-h-0 p-3">
        <TerminalOutput projectId={projectId} fetchOutput={getSwarmOutput} isRunning={project?.status === 'running'} />
      </div>
    </div>
  )
}

function LogsPanel() {
  const { projectId, wsEvents } = useWorkspace()
  return (
    <div className="lu-dock-panel">
      <div className="flex-1 min-h-0 p-3">
        <Suspense fallback={<PanelLoading label="logs" />}>
          <LogViewer projectId={projectId} wsEvents={wsEvents} />
        </Suspense>
      </div>
    </div>
  )
}

function HistoryPanel() {
  const { projectId } = useWorkspace()
  return (
    <div className="lu-dock-panel">
      <div className="flex-1 min-h-0 overflow-y-auto p-4">
        <Suspense fallback={<PanelLoading label="history" />}>
          <SwarmHistory projectId={projectId} fetchHistory={getSwarmHistory} />
        </Suspense>
      </div>
    </div>
  )
}

function FilesPanel() {
  const { projectId, wsEvents } = useWorkspace()
  return (
    <div className="lu-dock-panel">
      <div className="flex-1 min-h-0 p-2 sm:p-3">
        <Suspense fallback={<PanelLoading label="editor" />}>
          <FileEditor projectId={projectId} wsEvents={wsEvents} />
        </Suspense>
      </div>
    </div>
  )
}

function AnalyticsPanel() {
  const { projectId } = useWorkspace()
  return (
    <div className="lu-dock-panel">
      <div className="flex-1 min-h-0 overflow-y-auto">
        <Suspense fallback={<PanelLoading label="analytics" />}>
          <Analytics projectId={projectId} />
        </Suspense>
      </div>
    </div>
  )
}

function SettingsPanel() {
  const { projectId, initialConfig } = useWorkspace()
  return (
    <div className="lu-dock-panel">
      <div className="flex-1 min-h-0 overflow-y-auto p-4 space-y-4">
        <ProjectSettings projectId={projectId} initialConfig={initialConfig} onSave={updateProjectConfig} />
        <WebhookManager projectId={projectId} />
      </div>
    </div>
  )
}

const DOCK_COMPONENTS = {
  navigator: NavigatorPanel,
  dashboard: DashboardPanel,
  output: OutputPanel,
  logs: LogsPanel,
  history: HistoryPanel,
  files: FilesPanel,
  analytics: AnalyticsPanel,
  settings: SettingsPanel,
}

/* Sensible default: Navigator | Dashboard-group (Dashboard·History·Files·
   Analytics·Settings tabs) | Terminal over Logs. */
function buildDefaultLayout(api) {
  api.clear()
  const nav = api.addPanel({ id: 'navigator', component: 'navigator', title: 'Navigator' })
  api.addPanel({ id: 'dashboard', component: 'dashboard', title: 'Dashboard', position: { referencePanel: 'navigator', direction: 'right' } })
  api.addPanel({ id: 'output', component: 'output', title: 'Terminal', position: { referencePanel: 'dashboard', direction: 'right' } })
  api.addPanel({ id: 'logs', component: 'logs', title: 'Logs', position: { referencePanel: 'output', direction: 'below' } })
  api.addPanel({ id: 'history', component: 'history', title: 'History', position: { referencePanel: 'dashboard', direction: 'within' } })
  api.addPanel({ id: 'files', component: 'files', title: 'Files', position: { referencePanel: 'dashboard', direction: 'within' } })
  api.addPanel({ id: 'analytics', component: 'analytics', title: 'Analytics', position: { referencePanel: 'dashboard', direction: 'within' } })
  api.addPanel({ id: 'settings', component: 'settings', title: 'Settings', position: { referencePanel: 'dashboard', direction: 'within' } })
  try { nav.api.setSize({ width: 260 }) } catch { /* sizing is best-effort */ }
  try { api.getPanel('dashboard')?.api.setActive() } catch { /* noop */ }
}

export default function ProjectWorkspace({ projectId, wsEvents, project, initialConfig, onProjectChange }) {
  const storageKey = `lu_dock_layout_${projectId}`
  const apiRef = useRef(null)
  const disposablesRef = useRef([])
  const [openIds, setOpenIds] = useState([])
  const [addOpen, setAddOpen] = useState(false)

  const ctxValue = useMemo(
    () => ({ projectId, wsEvents, project, initialConfig, onProjectChange }),
    [projectId, wsEvents, project, initialConfig, onProjectChange],
  )

  const persist = useCallback((api) => {
    try { localStorage.setItem(storageKey, JSON.stringify(api.toJSON())) } catch { /* quota / disabled */ }
  }, [storageKey])

  const onReady = useCallback((event) => {
    const api = event.api
    apiRef.current = api

    let restored = false
    try {
      const saved = localStorage.getItem(storageKey)
      if (saved) {
        api.fromJSON(JSON.parse(saved))
        restored = api.panels.length > 0
      }
    } catch {
      restored = false // corrupt layout → fall back to default
    }
    if (!restored) {
      buildDefaultLayout(api)
      persist(api) // save the default so a drag-free session still restores it
    }

    setOpenIds(api.panels.map((p) => p.id))
    const d = api.onDidLayoutChange(() => {
      persist(api)
      setOpenIds(api.panels.map((p) => p.id))
    })
    disposablesRef.current = [d]
  }, [storageKey, persist])

  useEffect(() => () => {
    disposablesRef.current.forEach((d) => { try { d.dispose() } catch { /* noop */ } })
    disposablesRef.current = []
  }, [])

  const resetLayout = useCallback(() => {
    const api = apiRef.current
    if (!api) return
    try { localStorage.removeItem(storageKey) } catch { /* noop */ }
    buildDefaultLayout(api)
    setOpenIds(api.panels.map((p) => p.id))
  }, [storageKey])

  const addPanel = useCallback((id) => {
    const api = apiRef.current
    if (!api || api.getPanel(id)) return
    const def = PANELS.find((p) => p.id === id)
    api.addPanel({ id, component: id, title: def?.title || id })
    api.getPanel(id)?.api.setActive()
    setAddOpen(false)
  }, [])

  const closedPanels = useMemo(
    () => PANELS.filter((p) => !openIds.includes(p.id)),
    [openIds],
  )

  return (
    <WorkspaceContext.Provider value={ctxValue}>
      <div className="flex-1 min-h-0 flex flex-col">
        {/* Workspace toolbar */}
        <div className="lu-workspace-toolbar">
          <span className="text-xs font-mono text-zinc-500 truncate">
            {project?.name ? <span className="text-zinc-300">{project.name}</span> : 'Workspace'}
          </span>
          <div className="ml-auto flex items-center gap-1.5 relative">
            <div className="relative">
              <button
                type="button"
                onClick={() => setAddOpen((v) => !v)}
                disabled={closedPanels.length === 0}
                aria-haspopup="menu"
                aria-expanded={addOpen}
                className="px-2 py-1 rounded text-[11px] font-mono text-zinc-400 hover:text-crt-green hover:bg-retro-grid bg-transparent border border-retro-border cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-default focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-crt-green"
                title="Add a closed panel back to the workspace"
              >
                + Add panel
              </button>
              {addOpen && closedPanels.length > 0 && (
                <div
                  role="menu"
                  className="absolute right-0 top-full mt-1 z-50 retro-panel py-1 min-w-[140px]"
                >
                  {closedPanels.map((p) => (
                    <button
                      key={p.id}
                      type="button"
                      role="menuitem"
                      onClick={() => addPanel(p.id)}
                      className="block w-full text-left px-3 py-1.5 text-xs font-mono text-zinc-300 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-crt-green"
                    >
                      {p.title}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <button
              type="button"
              onClick={resetLayout}
              className="px-2 py-1 rounded text-[11px] font-mono text-zinc-400 hover:text-crt-green hover:bg-retro-grid bg-transparent border border-retro-border cursor-pointer transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-crt-green"
              title="Reset the workspace to the default layout"
            >
              Reset layout
            </button>
          </div>
        </div>

        {/* Dock surface */}
        <div className="flex-1 min-h-0">
          <DockviewReact
            key={projectId}
            className="lu-dock dockview-theme-dark"
            components={DOCK_COMPONENTS}
            onReady={onReady}
            disableFloatingGroups={false}
          />
        </div>
      </div>
    </WorkspaceContext.Provider>
  )
}
