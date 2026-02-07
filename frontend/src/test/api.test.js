import { describe, it, expect, vi, beforeEach } from 'vitest'

// Mock fetch globally
const mockFetch = vi.fn()
global.fetch = mockFetch

// Import after mocking
const api = await import('../lib/api.js')

beforeEach(() => {
  mockFetch.mockReset()
})

function jsonResponse(data, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  })
}

function emptyResponse(status = 204) {
  return Promise.resolve({
    ok: true,
    status,
    statusText: 'No Content',
    json: () => Promise.resolve(null),
    text: () => Promise.resolve(''),
  })
}

describe('API Client', () => {
  describe('getProjects', () => {
    it('fetches projects from /api/projects', async () => {
      const projects = [{ id: 1, name: 'Test' }]
      mockFetch.mockReturnValue(jsonResponse(projects))

      const result = await api.getProjects()
      expect(result).toEqual(projects)
      expect(mockFetch).toHaveBeenCalledWith('/api/projects', expect.objectContaining({
        headers: expect.objectContaining({ 'Content-Type': 'application/json' }),
      }))
    })
  })

  describe('getProject', () => {
    it('fetches a single project by ID', async () => {
      const project = { id: 1, name: 'Test', goal: 'Test goal' }
      mockFetch.mockReturnValue(jsonResponse(project))

      const result = await api.getProject(1)
      expect(result).toEqual(project)
      expect(mockFetch).toHaveBeenCalledWith('/api/projects/1', expect.any(Object))
    })
  })

  describe('createProject', () => {
    it('POSTs to /api/projects with JSON body', async () => {
      const data = { name: 'New', goal: 'Build', folder_path: '/tmp' }
      const created = { id: 1, ...data }
      mockFetch.mockReturnValue(jsonResponse(created, 201))

      const result = await api.createProject(data)
      expect(result).toEqual(created)
      expect(mockFetch).toHaveBeenCalledWith('/api/projects', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(data),
      }))
    })
  })

  describe('updateProject', () => {
    it('PATCHes a project with partial data', async () => {
      const update = { name: 'Updated' }
      mockFetch.mockReturnValue(jsonResponse({ id: 1, name: 'Updated' }))

      await api.updateProject(1, update)
      expect(mockFetch).toHaveBeenCalledWith('/api/projects/1', expect.objectContaining({
        method: 'PATCH',
        body: JSON.stringify(update),
      }))
    })
  })

  describe('deleteProject', () => {
    it('DELETEs a project and returns null for 204', async () => {
      mockFetch.mockReturnValue(emptyResponse(204))

      const result = await api.deleteProject(1)
      expect(result).toBeNull()
      expect(mockFetch).toHaveBeenCalledWith('/api/projects/1', expect.objectContaining({
        method: 'DELETE',
      }))
    })
  })

  describe('launchSwarm', () => {
    it('POSTs launch request with config', async () => {
      const config = { project_id: 1, resume: false, agent_count: 4, max_phases: 3 }
      mockFetch.mockReturnValue(jsonResponse({ status: 'launched', pid: 1234 }))

      const result = await api.launchSwarm(config)
      expect(result.status).toBe('launched')
      expect(mockFetch).toHaveBeenCalledWith('/api/swarm/launch', expect.objectContaining({
        method: 'POST',
        body: JSON.stringify(config),
      }))
    })
  })

  describe('stopSwarm', () => {
    it('POSTs stop request', async () => {
      mockFetch.mockReturnValue(jsonResponse({ status: 'stopped' }))

      const result = await api.stopSwarm({ project_id: 1 })
      expect(result.status).toBe('stopped')
    })
  })

  describe('getSwarmStatus', () => {
    it('GETs swarm status for a project', async () => {
      const status = { project_id: 1, agents: [], signals: {}, tasks: { total: 10, done: 5 } }
      mockFetch.mockReturnValue(jsonResponse(status))

      const result = await api.getSwarmStatus(1)
      expect(result.tasks.total).toBe(10)
      expect(mockFetch).toHaveBeenCalledWith('/api/swarm/status/1', expect.any(Object))
    })
  })

  describe('getFile', () => {
    it('GETs file content with project_id query param', async () => {
      mockFetch.mockReturnValue(jsonResponse({ path: 'tasks/TASKS.md', content: '# Tasks' }))

      const result = await api.getFile('tasks/TASKS.md', 1)
      expect(result.content).toBe('# Tasks')
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/files/tasks/TASKS.md?project_id=1',
        expect.any(Object),
      )
    })
  })

  describe('putFile', () => {
    it('PUTs file content', async () => {
      mockFetch.mockReturnValue(jsonResponse({ path: 'tasks/TASKS.md', status: 'written' }))

      await api.putFile('tasks/TASKS.md', '# Updated', 1)
      expect(mockFetch).toHaveBeenCalledWith('/api/files/tasks/TASKS.md', expect.objectContaining({
        method: 'PUT',
        body: JSON.stringify({ content: '# Updated', project_id: 1 }),
      }))
    })
  })

  describe('getLogs', () => {
    it('GETs logs with project_id and line limit', async () => {
      mockFetch.mockReturnValue(jsonResponse({ logs: [{ agent: 'Claude-1', lines: ['line1'] }] }))

      const result = await api.getLogs(1, 50)
      expect(result.logs[0].agent).toBe('Claude-1')
      expect(mockFetch).toHaveBeenCalledWith(
        '/api/logs?project_id=1&lines=50',
        expect.any(Object),
      )
    })
  })

  describe('error handling', () => {
    it('throws on non-ok responses', async () => {
      mockFetch.mockReturnValue(Promise.resolve({
        ok: false,
        status: 404,
        statusText: 'Not Found',
        text: () => Promise.resolve('Project not found'),
      }))

      await expect(api.getProject(999)).rejects.toThrow('404: Project not found')
    })
  })
})
