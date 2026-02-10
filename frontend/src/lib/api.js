const BASE = '/api'

// Auth helpers
const API_KEY_STORAGE = 'lu_api_key'

export function setApiKey(key) {
  if (key) {
    localStorage.setItem(API_KEY_STORAGE, key)
  } else {
    localStorage.removeItem(API_KEY_STORAGE)
  }
}

export function clearApiKey() {
  localStorage.removeItem(API_KEY_STORAGE)
}

export function getStoredApiKey() {
  return localStorage.getItem(API_KEY_STORAGE)
}

async function request(path, options = {}) {
  const headers = { 'Content-Type': 'application/json', ...options.headers }

  const apiKey = localStorage.getItem(API_KEY_STORAGE)
  if (apiKey) {
    headers['Authorization'] = `Bearer ${apiKey}`
  }

  const res = await fetch(`${BASE}${path}`, { ...options, headers })

  if (res.status === 401) {
    window.dispatchEvent(new CustomEvent('auth-required'))
    throw new Error('Authentication required')
  }
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
export const sendSwarmInput = (projectId, text) =>
  request('/swarm/input', { method: 'POST', body: JSON.stringify({ project_id: projectId, text }) })

// Files
export const getFile = (path, projectId) => request(`/files/${path}?project_id=${projectId}`)
export const putFile = (path, content, projectId) =>
  request(`/files/${path}`, { method: 'PUT', body: JSON.stringify({ content, project_id: projectId }) })

// Logs
export const getLogs = (projectId, lines = 100) => request(`/logs?project_id=${projectId}&lines=${lines}`)

export function searchLogs(projectId, { q, agent, level, from_date, to_date } = {}) {
  const params = new URLSearchParams({ project_id: projectId })
  if (q) params.set('q', q)
  if (agent) params.set('agent', agent)
  if (level) params.set('level', level)
  if (from_date) params.set('from_date', from_date)
  if (to_date) params.set('to_date', to_date)
  return request(`/logs/search?${params}`)
}

// Swarm History & Output
export const getSwarmHistory = (projectId) => request(`/swarm/history/${projectId}`)
export const getSwarmOutput = (projectId, offset = 0) => request(`/swarm/output/${projectId}?offset=${offset}`)

// Project Stats & Config
export const getProjectStats = (projectId) => request(`/projects/${projectId}/stats`)
export const updateProjectConfig = (projectId, config) =>
  request(`/projects/${projectId}/config`, { method: 'PATCH', body: JSON.stringify(config) })

// Browse directories
export const browseDirectory = (path = '') => {
  const params = new URLSearchParams()
  if (path) params.set('path', path)
  return request(`/browse?${params}`)
}

// Templates
export const getTemplates = () => request('/templates')
export const getTemplate = (id) => request(`/templates/${id}`)
export const createTemplate = (data) => request('/templates', { method: 'POST', body: JSON.stringify(data) })
export const updateTemplate = (id, data) => request(`/templates/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const deleteTemplate = (id) => request(`/templates/${id}`, { method: 'DELETE' })

// Webhooks
export const getWebhooks = () => request('/webhooks')
export const createWebhook = (data) => request('/webhooks', { method: 'POST', body: JSON.stringify(data) })
export const updateWebhook = (id, data) => request(`/webhooks/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const deleteWebhook = (id) => request(`/webhooks/${id}`, { method: 'DELETE' })

// Project archival
export const archiveProject = (id) => request(`/projects/${id}/archive`, { method: 'POST' })
export const unarchiveProject = (id) => request(`/projects/${id}/unarchive`, { method: 'POST' })

// Projects with archive filter
export const getProjectsWithArchived = (includeArchived = false) => {
  const params = new URLSearchParams()
  if (includeArchived) params.set('include_archived', 'true')
  const qs = params.toString()
  return request(`/projects${qs ? '?' + qs : ''}`)
}

// Watchers
export const startWatch = (projectId) => request(`/watch/${projectId}`, { method: 'POST' })
export const stopWatch = (projectId) => request(`/unwatch/${projectId}`, { method: 'POST' })
