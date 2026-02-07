import { useState, useEffect, useCallback } from 'react'
import { Routes, Route } from 'react-router-dom'
import { getProjects } from './lib/api'
import { useWebSocket } from './hooks/useWebSocket'
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
            <div className={`flex items-center gap-1.5 ${connected ? 'opacity-50' : 'opacity-100'}`}>
              <span className={`w-1.5 h-1.5 rounded-full ${connected ? 'led-active' : 'led-danger animate-pulse'}`} />
              <span className="text-[10px] text-zinc-500 font-mono">{connected ? 'ONLINE' : 'OFFLINE'}</span>
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
