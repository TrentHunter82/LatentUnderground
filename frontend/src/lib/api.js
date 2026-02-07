const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (res.status === 204) return null
  if (!res.ok) {
    const text = await res.text().catch(() => res.statusText)
    throw new Error(`${res.status}: ${text}`)
  }
  return res.json()
}

// Projects
export const getProjects = () => request('/projects')
export const getProject = (id) => request(`/projects/${id}`)
export const createProject = (data) => request('/projects', { method: 'POST', body: JSON.stringify(data) })
export const updateProject = (id, data) => request(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const deleteProject = (id) => request(`/projects/${id}`, { method: 'DELETE' })

// Swarm
export const launchSwarm = (data) => request('/swarm/launch', { method: 'POST', body: JSON.stringify(data) })
export const stopSwarm = (data) => request('/swarm/stop', { method: 'POST', body: JSON.stringify(data) })
export const getSwarmStatus = (projectId) => request(`/swarm/status/${projectId}`)

// Files
export const getFile = (path, projectId) => request(`/files/${path}?project_id=${projectId}`)
export const putFile = (path, content, projectId) =>
  request(`/files/${path}`, { method: 'PUT', body: JSON.stringify({ content, project_id: projectId }) })

// Logs
export const getLogs = (projectId, lines = 100) => request(`/logs?project_id=${projectId}&lines=${lines}`)

// Swarm History & Output
export const getSwarmHistory = (projectId) => request(`/swarm/history/${projectId}`)
export const getSwarmOutput = (projectId, offset = 0) => request(`/swarm/output/${projectId}?offset=${offset}`)

// Project Stats & Config
export const getProjectStats = (projectId) => request(`/projects/${projectId}/stats`)
export const updateProjectConfig = (projectId, config) =>
  request(`/projects/${projectId}/config`, { method: 'PATCH', body: JSON.stringify(config) })

// Watchers
export const startWatch = (projectId) => request(`/watch/${projectId}`, { method: 'POST' })
export const stopWatch = (projectId) => request(`/unwatch/${projectId}`, { method: 'POST' })
