import { useState, useEffect, useCallback } from 'react'
import { Routes, Route } from 'react-router-dom'
import { getProjects } from './lib/api'
import { useWebSocket } from './hooks/useWebSocket'
import { useHealthCheck } from './hooks/useHealthCheck'
import { useNotifications } from './hooks/useNotifications'
import Sidebar from './components/Sidebar'
import Home from './components/Home'
import NewProject from './components/NewProject'
import ProjectView from './components/ProjectView'
import ErrorBoundary from './components/ErrorBoundary'
import ThemeToggle from './components/ThemeToggle'

export default function App() {
  const [projects, setProjects] = useState([])
  const [wsEvent, setWsEvent] = useState(null)
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false)

  const { connected } = useWebSocket(setWsEvent)
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

  const refreshProjects = useCallback(async () => {
    try {
      const data = await getProjects()
      setProjects(data)
    } catch {}
  }, [])

  useEffect(() => {
    refreshProjects()
  }, [refreshProjects])

  const toggleSidebar = () => setSidebarCollapsed((c) => !c)

  return (
    <div className="crt-frame flex h-screen bg-zinc-950 retro-grid-bg">
      <Sidebar
        projects={projects}
        onRefresh={refreshProjects}
        collapsed={sidebarCollapsed}
        onToggle={toggleSidebar}
      />

      <main className="flex-1 flex flex-col min-h-0 relative">
        {/* Top bar */}
        <div className="flex items-center justify-between px-3 py-1.5 shrink-0 border-b border-retro-border">
          <button
            onClick={toggleSidebar}
            className="p-1.5 rounded-md text-zinc-400 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
            title={sidebarCollapsed ? 'Open sidebar' : 'Close sidebar'}
          >
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M3 5h12M3 9h12M3 13h12" />
            </svg>
          </button>

          <div className="flex items-center gap-2">
            <ThemeToggle />
            <div className="group relative flex items-center gap-1.5 cursor-default">
              <span className={`w-1.5 h-1.5 rounded-full ${
                healthStatus === 'healthy' && connected ? 'led-active' :
                healthStatus === 'slow' ? 'led-warning' :
                healthStatus === 'degraded' ? 'led-danger' :
                'led-danger animate-pulse'
              }`} />
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

        <ErrorBoundary>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/projects/new" element={<NewProject onProjectChange={refreshProjects} />} />
            <Route path="/projects/:id" element={<ProjectView wsEvents={wsEvent} onProjectChange={refreshProjects} />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </div>
  )
}
