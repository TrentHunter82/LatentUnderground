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

// AbortController-aware request: pass { signal } in options to cancel in-flight requests
export function createAbortable() {
  const controller = new AbortController()
  return {
    signal: controller.signal,
    abort: () => controller.abort(),
  }
}

// Projects
export const getProjects = (opts) => request('/projects', opts)
export const getProject = (id, opts) => request(`/projects/${id}`, opts)
export const createProject = (data) => request('/projects', { method: 'POST', body: JSON.stringify(data) })
export const updateProject = (id, data) => request(`/projects/${id}`, { method: 'PATCH', body: JSON.stringify(data) })
export const deleteProject = (id) => request(`/projects/${id}`, { method: 'DELETE' })

// Swarm
export const launchSwarm = (data) => request('/swarm/launch', { method: 'POST', body: JSON.stringify(data) })
export const stopSwarm = (data) => request('/swarm/stop', { method: 'POST', body: JSON.stringify(data) })
export const getSwarmStatus = (projectId, opts) => request(`/swarm/status/${projectId}`, opts)
export const sendSwarmInput = (projectId, text, agent = null) =>
  request('/swarm/input', { method: 'POST', body: JSON.stringify({ project_id: projectId, text, agent }) })
export const getSwarmAgents = (projectId, opts) => request(`/swarm/agents/${projectId}`, opts)
export const stopSwarmAgent = (projectId, agentName) =>
  request(`/swarm/agents/${projectId}/${agentName}/stop`, { method: 'POST' })

// Files
export const getFile = (path, projectId) => request(`/files/${path}?project_id=${projectId}`)
export const putFile = (path, content, projectId) =>
  request(`/files/${path}`, { method: 'PUT', body: JSON.stringify({ content, project_id: projectId }) })

// Logs
export const getLogs = (projectId, lines = 100, opts) => request(`/logs?project_id=${projectId}&lines=${lines}`, opts)

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
export const getSwarmHistory = (projectId, opts) => request(`/swarm/history/${projectId}`, opts)
export const getSwarmOutput = (projectId, offset = 0, agent = null, opts) => {
  const params = new URLSearchParams({ offset })
  if (agent) params.set('agent', agent)
  return request(`/swarm/output/${projectId}?${params}`, opts)
}

// Project Stats & Config
export const getProjectStats = (projectId, opts) => request(`/projects/${projectId}/stats`, opts)
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

// Agent events
export const getAgentEvents = (projectId, { agent, event_type, from, to, limit = 100, offset = 0 } = {}, opts) => {
  const params = new URLSearchParams()
  if (agent) params.set('agent', agent)
  if (event_type) params.set('event_type', event_type)
  if (from) params.set('from', from)
  if (to) params.set('to', to)
  if (limit) params.set('limit', limit)
  if (offset) params.set('offset', offset)
  const qs = params.toString()
  return request(`/swarm/events/${projectId}${qs ? '?' + qs : ''}`, opts)
}

// Output search
export const searchSwarmOutput = (projectId, { q, agent, limit = 50, context } = {}, opts) => {
  const params = new URLSearchParams()
  if (q) params.set('q', q)
  if (agent) params.set('agent', agent)
  if (limit) params.set('limit', limit)
  if (context !== undefined) params.set('context', context)
  return request(`/swarm/output/${projectId}/search?${params}`, opts)
}

// Run comparison
export const compareRuns = (runA, runB, opts) =>
  request(`/swarm/runs/compare?run_a=${runA}&run_b=${runB}`, opts)

// Agent directives
export const sendDirective = (projectId, agentName, text, priority = 'normal') =>
  request(`/swarm/agents/${projectId}/${agentName}/directive`, {
    method: 'POST',
    body: JSON.stringify({ text, priority }),
  })

export const getDirectiveStatus = (projectId, agentName, opts) =>
  request(`/swarm/agents/${projectId}/${agentName}/directive`, opts)

// Agent prompt
export const updateAgentPrompt = (projectId, agentName, content) =>
  request(`/swarm/agents/${projectId}/${agentName}/prompt`, {
    method: 'PUT',
    body: JSON.stringify({ prompt: content }),
  })

// Agent restart
export const restartAgent = (projectId, agentName) =>
  request(`/swarm/agents/${projectId}/${agentName}/restart`, { method: 'POST' })

// System & Operations
export const getSystemInfo = (opts) => request('/system', opts)
export const getSystemHealth = (opts) => request('/health', opts)
export const getMetrics = (opts) => request('/metrics', opts)
export const getHealthTrends = (opts) => request('/system/health/trends', opts)

// Project health & quota
export const getProjectHealth = (projectId, opts) => request(`/projects/${projectId}/health`, opts)
export const getProjectQuota = (projectId, opts) => request(`/projects/${projectId}/quota`, opts)

// Guardrails
export const getProjectGuardrails = (projectId, opts) => request(`/projects/${projectId}/guardrails`, opts)

// Agent checkpoints
export const getRunCheckpoints = (runId, { agent } = {}, opts) => {
  const params = new URLSearchParams()
  if (agent) params.set('agent', agent)
  const qs = params.toString()
  return request(`/swarm/runs/${runId}/checkpoints${qs ? '?' + qs : ''}`, opts)
}

// Agent logs & output tail
export const getAgentLogs = (projectId, agentName, lines = 100, opts) =>
  request(`/swarm/agents/${projectId}/${agentName}/logs?lines=${lines}`, opts)
export const getOutputTail = (projectId, lines = 50, agent = null, opts) => {
  const params = new URLSearchParams({ lines })
  if (agent) params.set('agent', agent)
  return request(`/swarm/output/${projectId}/tail?${params}`, opts)
}

// Watchers
export const startWatch = (projectId) => request(`/watch/${projectId}`, { method: 'POST' })
export const stopWatch = (projectId) => request(`/unwatch/${projectId}`, { method: 'POST' })
