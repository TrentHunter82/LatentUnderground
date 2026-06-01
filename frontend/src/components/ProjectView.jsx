import { useMemo } from 'react'
import { useParams } from 'react-router-dom'
import ProjectWorkspace from './ProjectWorkspace'
import { useProject } from '../hooks/useProjectQuery'

export default function ProjectView({ wsEvents, onProjectChange }) {
  const { id } = useParams()
  const projectId = Number(id)

  // Use TanStack Query for project data
  const { data: project } = useProject(projectId, {
    refetchOnWindowFocus: true,
  })

  const initialConfig = useMemo(() => {
    if (!project?.config) return null
    try { return JSON.parse(project.config) } catch (e) { console.warn('Failed to parse project config:', e); return null }
  }, [project])

  return (
    <ProjectWorkspace
      projectId={projectId}
      wsEvents={wsEvents}
      project={project}
      initialConfig={initialConfig}
      onProjectChange={onProjectChange}
    />
  )
}
