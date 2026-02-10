import { useState, useEffect, useCallback, lazy, Suspense } from 'react'
import { Routes, Route, useNavigate } from 'react-router-dom'
import { getProjects, getProjectsWithArchived } from './lib/api'
import { useWebSocket } from './hooks/useWebSocket'
import { useHealthCheck } from './hooks/useHealthCheck'
import { useNotifications } from './hooks/useNotifications'
import Sidebar from './components/Sidebar'
import Home from './components/Home'
import ErrorBoundary from './components/ErrorBoundary'
import ThemeToggle from './components/ThemeToggle'

// Lazy-load route components and modals for bundle splitting
const NewProject = lazy(() => import('./components/NewProject'))
const ProjectView = lazy(() => import('./components/ProjectView'))
const AuthModal = lazy(() => import('./components/AuthModal'))
const SettingsPanel = lazy(() => import('./components/SettingsPanel'))
const ShortcutCheatsheet = lazy(() => import('./components/ShortcutCheatsheet'))
const OnboardingModal = lazy(() => import('./components/OnboardingModal'))

export default function App() {
  const [projects, setProjects] = useState([])
  const [wsEvent, setWsEvent] = useState(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)
  const [showAuth, setShowAuth] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [showShortcuts, setShowShortcuts] = useState(false)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [showArchived, setShowArchived] = useState(false)
  const navigate = useNavigate()

  const { connected, reconnecting } = useWebSocket(setWsEvent)
  const { status: healthStatus, latency } = useHealthCheck()
  const { notify } = useNotifications()

  // Fire browser notification on swarm complete/failed
  useEffect(() => {
    if (!wsEvent) return
    if (wsEvent.type === 'swarm_complete') {
      notify('Swarm Complete', { body: 'All agents have finished successfully.' })
    } else if (wsEvent.type === 'swarm_failed') {
      notify('Swarm Failed', { body: wsEvent.error || 'The swarm encountered an error.' })
    }
  }, [wsEvent, notify])

  // Listen for 401 auth-required events from api.js
  useEffect(() => {
    const handler = () => setShowAuth(true)
    window.addEventListener('auth-required', handler)
    return () => window.removeEventListener('auth-required', handler)
  }, [])

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (e) => {
      const isMod = e.ctrlKey || e.metaKey

      if (isMod && e.key === 'k') {
        e.preventDefault()
        const searchInput = document.getElementById('sidebar-search')
        if (searchInput) {
          setSidebarCollapsed(false)
          setTimeout(() => searchInput.focus(), 100)
        }
      } else if (isMod && e.key === 'n') {
        e.preventDefault()
        navigate('/projects/new')
      } else if (isMod && (e.key === '?' || (e.shiftKey && e.key === '/'))) {
        e.preventDefault()
        setShowShortcuts((v) => !v)
      } else if (e.key === 'Escape') {
        setShowAuth(false)
        setShowSettings(false)
        setShowShortcuts(false)
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [navigate])

  const refreshProjects = useCallback(async () => {
    try {
      const data = showArchived ? await getProjectsWithArchived(true) : await getProjects()
      setProjects(data)
    } catch (e) {
      console.warn('Failed to refresh projects:', e)
    }
  }, [showArchived])

  useEffect(() => {
    refreshProjects()
  }, [refreshProjects])

  // Show onboarding when no projects and not previously dismissed
  useEffect(() => {
    if (projects.length === 0 && !localStorage.getItem('lu_onboarding_complete')) {
      setShowOnboarding(true)
    }
  }, [projects])

  const toggleSidebar = () => setSidebarCollapsed((c) => !c)

  return (
    <div className="crt-frame flex h-screen bg-zinc-950 retro-grid-bg">
      <Sidebar
        projects={projects}
        onRefresh={refreshProjects}
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
        showArchived={showArchived}
        onShowArchivedChange={setShowArchived}
      />

      <main className="flex-1 flex flex-col min-h-0 relative">
        {/* Top bar */}
        <div className="flex items-center justify-between px-3 py-1.5 shrink-0 border-b border-retro-border">
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-md text-zinc-400 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
            title={sidebarCollapsed ? 'Open sidebar' : 'Close sidebar'}
            aria-label={sidebarCollapsed ? 'Open sidebar' : 'Close sidebar'}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 5h12M3 9h12M3 13h12" />
            </svg>
          </button>

          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowShortcuts(true)}
              className="p-1.5 rounded-md text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
              title="Keyboard shortcuts (Ctrl+?)"
              aria-label="Keyboard shortcuts"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <rect x="1" y="4" width="14" height="9" rx="1.5" />
                <path d="M4 7h1M7 7h2M11 7h1M5 10h6" />
              </svg>
            </button>
            <button
              onClick={() => setShowSettings(true)}
              className="p-1.5 rounded-md text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
              title="Settings"
              aria-label="Open settings"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                <path d="M6.86 2.07a1.12 1.12 0 012.28 0l.23 1.14a.67.67 0 00.88.47l1.07-.48a1.12 1.12 0 011.61 1.14l-.25 1.13a.67.67 0 00.47.78l1.14.38a1.12 1.12 0 01.2 2.09l-1.01.6a.67.67 0 00-.25.9l.55 1.03a1.12 1.12 0 01-1.14 1.61l-1.13-.25a.67.67 0 00-.78.47l-.38 1.14a1.12 1.12 0 01-2.09.2l-.6-1.01a.67.67 0 00-.9-.25l-1.03.55a1.12 1.12 0 01-1.61-1.14l.25-1.13a.67.67 0 00-.47-.78l-1.14-.38a1.12 1.12 0 01-.2-2.09l1.01-.6a.67.67 0 00.25-.9L3.48 4.4a1.12 1.12 0 011.14-1.61l1.13.25a.67.67 0 00.78-.47z" />
                <circle cx="8" cy="8" r="2" />
              </svg>
            </button>
            <ThemeToggle />
            <div className="group relative flex items-center gap-1.5 cursor-default">
              <span
                className={`w-1.5 h-1.5 rounded-full ${
                  healthStatus === 'healthy' && connected ? 'led-active' :
                  healthStatus === 'slow' ? 'led-warning' :
                  healthStatus === 'degraded' ? 'led-danger' :
                  'led-danger animate-pulse'
                }`}
                aria-label={`System status: ${
                  healthStatus === 'healthy' && connected ? 'online' :
                  healthStatus === 'slow' ? 'slow' :
                  healthStatus === 'degraded' ? 'degraded' : 'offline'
                }`}
              />
              <span className="text-[10px] text-zinc-500 font-mono">{
                healthStatus === 'healthy' && connected ? 'ONLINE' :
                healthStatus === 'slow' ? 'SLOW' :
                healthStatus === 'degraded' ? 'DEGRADED' :
                'OFFLINE'
              }</span>
              {/* Tooltip */}
              <div className="absolute right-0 top-full mt-1 hidden group-hover:block bg-retro-dark border border-retro-border rounded px-2.5 py-1.5 text-[10px] font-mono whitespace-nowrap z-50 shadow-lg">
                <div className="text-zinc-400">WS: <span className={connected ? 'text-crt-green' : 'text-signal-red'}>{connected ? 'connected' : 'disconnected'}</span></div>
                <div className="text-zinc-400">API: <span className={
                  healthStatus === 'healthy' ? 'text-crt-green' :
                  healthStatus === 'slow' ? 'text-signal-yellow' :
                  'text-signal-red'
                }>{healthStatus}</span></div>
                {latency !== null && <div className="text-zinc-500">Latency: {latency}ms</div>}
              </div>
            </div>
          </div>
        </div>

        {/* WebSocket reconnection banner */}
        {reconnecting && (
          <div className="px-3 py-1.5 bg-signal-amber/10 border-b border-signal-amber/30 flex items-center gap-2 text-xs font-mono text-signal-amber shrink-0" role="status" aria-live="polite">
            <span className="w-2 h-2 rounded-full bg-signal-amber animate-pulse shrink-0" />
            <span>Reconnecting to server...</span>
          </div>
        )}

        <ErrorBoundary>
          <Suspense fallback={<div className="flex-1 flex items-center justify-center text-zinc-500 font-mono text-sm">Loading...</div>}>
            <Routes>
              <Route path="/" element={<Home />} />
              <Route path="/projects/new" element={<NewProject onProjectChange={refreshProjects} />} />
              <Route path="/projects/:id" element={<ProjectView wsEvents={wsEvent} onProjectChange={refreshProjects} />} />
            </Routes>
          </Suspense>
        </ErrorBoundary>
      </main>

      <Suspense fallback={null}>
        {showAuth && <AuthModal open={showAuth} onClose={() => setShowAuth(false)} />}
        {showSettings && <SettingsPanel
          open={showSettings}
          onClose={() => setShowSettings(false)}
          onOpenAuth={() => { setShowSettings(false); setShowAuth(true) }}
        />}
        {showShortcuts && <ShortcutCheatsheet open={showShortcuts} onClose={() => setShowShortcuts(false)} />}
        {showOnboarding && <OnboardingModal open={showOnboarding} onClose={() => setShowOnboarding(false)} />}
      </Suspense>
    </div>
  )
}
