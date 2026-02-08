import { useState, useEffect, useMemo, useRef, useCallback } from 'react'
import Dashboard from './Dashboard'
import FileEditor from './FileEditor'
import LogViewer from './LogViewer'
import SwarmHistory from './SwarmHistory'
import TerminalOutput from './TerminalOutput'
import Analytics from './Analytics'
import ProjectSettings from './ProjectSettings'
import { useParams } from 'react-router-dom'
import { getProject, getSwarmHistory, getSwarmOutput, updateProjectConfig } from '../lib/api'

const tabs = [
  { id: 'dashboard', label: 'Dashboard' },
  { id: 'history', label: 'History' },
  { id: 'output', label: 'Output' },
  { id: 'files', label: 'Files' },
  { id: 'logs', label: 'Logs' },
  { id: 'analytics', label: 'Analytics' },
  { id: 'settings', label: 'Settings' },
]

export default function ProjectView({ wsEvents, onProjectChange }) {
  const { id } = useParams()
  const projectId = Number(id)
  const [activeTab, setActiveTab] = useState('dashboard')
  const [project, setProject] = useState(null)

  useEffect(() => {
    getProject(projectId).then(setProject).catch((e) => console.warn('Failed to load project:', e))
  }, [projectId])

  const initialConfig = useMemo(() => {
    if (!project?.config) return null
    try { return JSON.parse(project.config) } catch (e) { console.warn('Failed to parse project config:', e); return null }
  }, [project])

  const tabRefs = useRef({})

  const handleTabKeyDown = useCallback((e) => {
    const idx = tabs.findIndex((t) => t.id === activeTab)
    let next = -1

    if (e.key === 'ArrowRight') next = (idx + 1) % tabs.length
    else if (e.key === 'ArrowLeft') next = (idx - 1 + tabs.length) % tabs.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = tabs.length - 1
    else return

    e.preventDefault()
    const nextId = tabs[next].id
    setActiveTab(nextId)
    tabRefs.current[nextId]?.focus()
  }, [activeTab])

  return (
    <div className="flex-1 flex flex-col min-h-0">
      {/* Tab bar */}
      <div role="tablist" aria-label="Project views" className="flex items-center gap-1 px-2 sm:px-4 pt-3 bg-zinc-950 border-b border-retro-border overflow-x-auto tab-scroll">
        {tabs.map((tab) => (
          <button
            key={tab.id}
            ref={(el) => { tabRefs.current[tab.id] = el }}
            id={`tab-${tab.id}`}
            role="tab"
            aria-selected={activeTab === tab.id}
            aria-controls={`tabpanel-${tab.id}`}
            tabIndex={activeTab === tab.id ? 0 : -1}
            onClick={() => setActiveTab(tab.id)}
            onKeyDown={handleTabKeyDown}
            className={`px-4 py-2 rounded-t text-sm font-medium transition-colors cursor-pointer border-0 font-mono whitespace-nowrap ${
              activeTab === tab.id
                ? 'bg-retro-grid text-crt-green border-b-2 border-crt-green'
                : 'text-zinc-500 hover:text-zinc-300 bg-transparent'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Tab content */}
      <div role="tabpanel" id={`tabpanel-${activeTab}`} aria-labelledby={`tab-${activeTab}`} className="flex-1 min-h-0 bg-zinc-950">
        {activeTab === 'dashboard' && (
          <Dashboard wsEvents={wsEvents} onProjectChange={onProjectChange} />
        )}
        {activeTab === 'files' && (
          <div className="p-4 h-full">
            <FileEditor projectId={projectId} wsEvents={wsEvents} />
          </div>
        )}
        {activeTab === 'history' && (
          <div className="p-4 h-full overflow-y-auto">
            <SwarmHistory projectId={projectId} fetchHistory={getSwarmHistory} />
          </div>
        )}
        {activeTab === 'output' && (
          <div className="p-4 h-full">
            <TerminalOutput projectId={projectId} fetchOutput={getSwarmOutput} isRunning={project?.status === 'running'} />
          </div>
        )}
        {activeTab === 'logs' && (
          <div className="p-4 h-full">
            <LogViewer projectId={projectId} wsEvents={wsEvents} />
          </div>
        )}
        {activeTab === 'analytics' && (
          <Analytics projectId={projectId} />
        )}
        {activeTab === 'settings' && (
          <div className="p-4 h-full overflow-y-auto">
            <ProjectSettings projectId={projectId} initialConfig={initialConfig} onSave={updateProjectConfig} />
          </div>
        )}
      </div>
    </div>
  )
}
