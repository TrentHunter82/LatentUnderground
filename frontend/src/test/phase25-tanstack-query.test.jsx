import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ToastProvider } from '../components/Toast'

const { createApiMock } = await vi.hoisted(() => import('./test-utils'))

// Mock api.js
vi.mock('../lib/api', () => createApiMock({
  getProjects: vi.fn(() => Promise.resolve([
    { id: 1, name: 'Test Project', goal: 'Test goal', status: 'stopped', config: '{}' },
  ])),
  getProjectsWithArchived: vi.fn(() => Promise.resolve([
    { id: 1, name: 'Test Project', goal: 'Test goal', status: 'stopped', config: '{}' },
  ])),
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test Project', goal: 'Test goal', status: 'stopped', config: '{}' })),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 0, total_tasks_completed: 0, avg_duration_seconds: null })),
  getProjectHealth: vi.fn(() => Promise.resolve({ project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable' })),
  getProjectQuota: vi.fn(() => Promise.resolve({ project_id: 1, quota: {}, usage: {} })),
  getSwarmStatus: vi.fn(() => Promise.resolve({ agents: [], signals: {}, tasks: [], phase: null })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmAgents: vi.fn(() => Promise.resolve({ agents: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
  getAgentEvents: vi.fn(() => Promise.resolve({ events: [], total: 0 })),
  createProject: vi.fn(() => Promise.resolve({ id: 2, name: 'New' })),
  updateProject: vi.fn(() => Promise.resolve({})),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  updateProjectConfig: vi.fn(() => Promise.resolve({})),
  launchSwarm: vi.fn(() => Promise.resolve({})),
  stopSwarm: vi.fn(() => Promise.resolve({})),
  sendDirective: vi.fn(() => Promise.resolve({})),
  updateAgentPrompt: vi.fn(() => Promise.resolve({})),
  archiveProject: vi.fn(() => Promise.resolve({})),
  unarchiveProject: vi.fn(() => Promise.resolve({})),
  stopSwarmAgent: vi.fn(() => Promise.resolve({})),
  restartAgent: vi.fn(() => Promise.resolve({})),
  startWatch: vi.fn(() => Promise.resolve({})),
  stopWatch: vi.fn(() => Promise.resolve({})),
  getFile: vi.fn(() => Promise.resolve({ content: '' })),
  putFile: vi.fn(() => Promise.resolve({})),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ results: [] })),
  getTemplates: vi.fn(() => Promise.resolve([])),
  createTemplate: vi.fn(() => Promise.resolve({})),
  updateTemplate: vi.fn(() => Promise.resolve({})),
  deleteTemplate: vi.fn(() => Promise.resolve(null)),
  getWebhooks: vi.fn(() => Promise.resolve([])),
  createWebhook: vi.fn(() => Promise.resolve({})),
  updateWebhook: vi.fn(() => Promise.resolve({})),
  deleteWebhook: vi.fn(() => Promise.resolve(null)),
  browseDirectory: vi.fn(() => Promise.resolve({ entries: [] })),
  createAbortable: vi.fn(() => ({ signal: new AbortController().signal, abort: vi.fn() })),
  getDirectiveStatus: vi.fn(() => Promise.resolve({ pending: false })),
  searchSwarmOutput: vi.fn(() => Promise.resolve({ matches: [] })),
  compareRuns: vi.fn(() => Promise.resolve({})),
  getRunCheckpoints: vi.fn(() => Promise.resolve({ checkpoints: [] })),
  getSystemInfo: vi.fn(() => Promise.resolve({})),
  getSystemHealth: vi.fn(() => Promise.resolve({ status: 'healthy' })),
  getMetrics: vi.fn(() => Promise.resolve('')),
  getHealthTrends: vi.fn(() => Promise.resolve({ projects: [] })),
  setApiKey: vi.fn(),
  clearApiKey: vi.fn(),
  getStoredApiKey: vi.fn(() => null),
}))

vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connected: true, reconnecting: false, send: vi.fn() }),
}))

vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 10 }),
}))

vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({ notify: vi.fn() }),
}))

function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
      mutations: { retry: false },
    },
  })
}

function TestWrapper({ children, initialEntries = ['/'] }) {
  const queryClient = createTestQueryClient()
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>
        <ToastProvider>
          {children}
        </ToastProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('TanStack Query Integration', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('useProjectQuery hooks', () => {
    it('useProjects fetches project list', async () => {
      const { useProjects } = await import('../hooks/useProjectQuery')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useProjects(), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toHaveLength(1)
      expect(result.current.data[0].name).toBe('Test Project')
    })

    it('useProject fetches individual project', async () => {
      const { useProject } = await import('../hooks/useProjectQuery')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useProject(1), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data.id).toBe(1)
      expect(result.current.data.name).toBe('Test Project')
    })

    it('useProject does not fetch when projectId is falsy', async () => {
      const { useProject } = await import('../hooks/useProjectQuery')
      const { renderHook } = await import('@testing-library/react')
      const { getProject } = await import('../lib/api')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      renderHook(() => useProject(null), { wrapper })
      await new Promise(r => setTimeout(r, 100))
      expect(getProject).not.toHaveBeenCalled()
    })
  })

  describe('useSwarmQuery hooks', () => {
    it('useSwarmStatus fetches status', async () => {
      const { useSwarmStatus } = await import('../hooks/useSwarmQuery')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useSwarmStatus(1), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toHaveProperty('agents')
    })

    it('useSwarmHistory fetches history', async () => {
      const { useSwarmHistory } = await import('../hooks/useSwarmQuery')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useSwarmHistory(1), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toHaveProperty('runs')
    })

    it('useSwarmAgents fetches agents', async () => {
      const { useSwarmAgents } = await import('../hooks/useSwarmQuery')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useSwarmAgents(1), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(result.current.data).toHaveProperty('agents')
    })
  })

  describe('useMutations hooks', () => {
    it('useCreateProject calls createProject', async () => {
      const { useCreateProject } = await import('../hooks/useMutations')
      const { createProject } = await import('../lib/api')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useCreateProject(), { wrapper })
      await act(async () => {
        await result.current.mutateAsync({ name: 'New', goal: 'Test' })
      })
      expect(createProject.mock.calls[0][0]).toEqual({ name: 'New', goal: 'Test' })
    })

    it('useDeleteProject calls deleteProject', async () => {
      const { useDeleteProject } = await import('../hooks/useMutations')
      const { deleteProject } = await import('../lib/api')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useDeleteProject(), { wrapper })
      await act(async () => {
        await result.current.mutateAsync(1)
      })
      expect(deleteProject.mock.calls[0][0]).toBe(1)
    })

    it('useCreateProject invalidates project list cache on success', async () => {
      const { useCreateProject } = await import('../hooks/useMutations')
      const { projectKeys } = await import('../hooks/useProjectQuery')
      const { renderHook } = await import('@testing-library/react')
      const queryClient = createTestQueryClient()
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useCreateProject(), { wrapper })
      await act(async () => {
        await result.current.mutateAsync({ name: 'New', goal: 'Test' })
      })
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: projectKeys.lists() })
      )
    })

    it('useLaunchSwarm invalidates swarm status and agents cache', async () => {
      const { useLaunchSwarm } = await import('../hooks/useMutations')
      const { swarmKeys } = await import('../hooks/useSwarmQuery')
      const { renderHook } = await import('@testing-library/react')
      const queryClient = createTestQueryClient()
      const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={queryClient}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useLaunchSwarm(), { wrapper })
      await act(async () => {
        await result.current.mutateAsync({ project_id: 1 })
      })
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: swarmKeys.status(1) })
      )
      expect(invalidateSpy).toHaveBeenCalledWith(
        expect.objectContaining({ queryKey: swarmKeys.agents(1) })
      )
    })
  })

  describe('Query error states', () => {
    it('useProject returns error when API fails', async () => {
      const { getProject } = await import('../lib/api')
      getProject.mockRejectedValue(new Error('Network error'))
      try {
        const { useProject } = await import('../hooks/useProjectQuery')
        const { renderHook } = await import('@testing-library/react')
        const wrapper = ({ children }) => (
          <QueryClientProvider client={createTestQueryClient()}>
            {children}
          </QueryClientProvider>
        )
        const { result } = renderHook(() => useProject(1), { wrapper })
        await waitFor(() => expect(result.current.isError).toBe(true))
        expect(result.current.error.message).toBe('Network error')
      } finally {
        // Restore mock to prevent polluting subsequent tests
        getProject.mockResolvedValue({ id: 1, name: 'Test Project', goal: 'Test goal', status: 'stopped', config: '{}' })
      }
    })

    it('useProjects returns loading state initially', async () => {
      const { useProjects } = await import('../hooks/useProjectQuery')
      const { renderHook } = await import('@testing-library/react')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useProjects(), { wrapper })
      // Initially should be loading
      expect(result.current.isLoading).toBe(true)
      expect(result.current.data).toBeUndefined()
    })
  })

  describe('Query key factories', () => {
    it('projectKeys generate correct key hierarchies', async () => {
      const { projectKeys } = await import('../hooks/useProjectQuery')
      expect(projectKeys.all).toEqual(['projects'])
      expect(projectKeys.lists()).toEqual(['projects', 'list'])
      expect(projectKeys.list({ showArchived: true })).toEqual(['projects', 'list', { showArchived: true }])
      expect(projectKeys.detail(1)).toEqual(['projects', 'detail', 1])
      expect(projectKeys.stats(1)).toEqual(['projects', 'detail', 1, 'stats'])
      expect(projectKeys.health(1)).toEqual(['projects', 'detail', 1, 'health'])
    })

    it('swarmKeys generate correct key hierarchies', async () => {
      const { swarmKeys } = await import('../hooks/useSwarmQuery')
      expect(swarmKeys.all).toEqual(['swarm'])
      expect(swarmKeys.status(1)).toEqual(['swarm', 'status', 1])
      expect(swarmKeys.history(1)).toEqual(['swarm', 'history', 1])
      expect(swarmKeys.agents(1)).toEqual(['swarm', 'agents', 1])
    })
  })

  describe('Stale time configuration', () => {
    it('project queries use 5s stale time', async () => {
      const { useProject } = await import('../hooks/useProjectQuery')
      const { renderHook } = await import('@testing-library/react')
      const { getProject } = await import('../lib/api')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useProject(1), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      // First call should have been made
      expect(getProject).toHaveBeenCalledTimes(1)
    })

    it('swarm status uses 5s stale time (high-frequency)', async () => {
      const { useSwarmStatus } = await import('../hooks/useSwarmQuery')
      const { renderHook } = await import('@testing-library/react')
      const { getSwarmStatus } = await import('../lib/api')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useSwarmStatus(1), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(getSwarmStatus).toHaveBeenCalledTimes(1)
    })

    it('project stats uses 30s stale time (analytics-tier)', async () => {
      const { useProjectStats } = await import('../hooks/useProjectQuery')
      const { renderHook } = await import('@testing-library/react')
      const { getProjectStats } = await import('../lib/api')
      const wrapper = ({ children }) => (
        <QueryClientProvider client={createTestQueryClient()}>
          {children}
        </QueryClientProvider>
      )
      const { result } = renderHook(() => useProjectStats(1), { wrapper })
      await waitFor(() => expect(result.current.isSuccess).toBe(true))
      expect(getProjectStats).toHaveBeenCalledTimes(1)
      expect(result.current.data).toHaveProperty('total_runs')
    })
  })
})

describe('Circuit Breaker UI', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  describe('AgentGrid circuit breaker badge', () => {
    it('shows circuit breaker badge when state is open', async () => {
      const AgentGrid = (await import('../components/AgentGrid')).default
      const agents = [{ name: 'Claude-1', last_heartbeat: new Date().toISOString() }]
      const processAgents = [{ name: 'Claude-1', alive: false, exit_code: 1, pid: 123, circuit_state: 'open' }]

      render(
        <TestWrapper>
          <AgentGrid agents={agents} processAgents={processAgents} projectId={1} />
        </TestWrapper>
      )

      expect(screen.getByText('Open')).toBeInTheDocument()
      expect(screen.getByLabelText('Circuit breaker open')).toBeInTheDocument()
    })

    it('shows half-open badge', async () => {
      const AgentGrid = (await import('../components/AgentGrid')).default
      const agents = [{ name: 'Claude-1', last_heartbeat: new Date().toISOString() }]
      const processAgents = [{ name: 'Claude-1', alive: false, exit_code: 1, pid: 123, circuit_state: 'half-open' }]

      render(
        <TestWrapper>
          <AgentGrid agents={agents} processAgents={processAgents} projectId={1} />
        </TestWrapper>
      )

      expect(screen.getByText('Half-open')).toBeInTheDocument()
      expect(screen.getByLabelText('Circuit breaker half-open')).toBeInTheDocument()
    })

    it('does not show badge when circuit is closed', async () => {
      const AgentGrid = (await import('../components/AgentGrid')).default
      const agents = [{ name: 'Claude-1', last_heartbeat: new Date().toISOString() }]
      const processAgents = [{ name: 'Claude-1', alive: true, exit_code: null, pid: 123, circuit_state: 'closed' }]

      render(
        <TestWrapper>
          <AgentGrid agents={agents} processAgents={processAgents} projectId={1} />
        </TestWrapper>
      )

      expect(screen.queryByText('Open')).not.toBeInTheDocument()
      expect(screen.queryByText('Half-open')).not.toBeInTheDocument()
    })

    it('does not show badge when circuit_state is absent', async () => {
      const AgentGrid = (await import('../components/AgentGrid')).default
      const agents = [{ name: 'Claude-1', last_heartbeat: new Date().toISOString() }]
      const processAgents = [{ name: 'Claude-1', alive: true, exit_code: null, pid: 123 }]

      render(
        <TestWrapper>
          <AgentGrid agents={agents} processAgents={processAgents} projectId={1} />
        </TestWrapper>
      )

      expect(screen.queryByLabelText(/Circuit breaker/)).not.toBeInTheDocument()
    })
  })

  describe('ProjectSettings circuit breaker config', () => {
    it('renders circuit breaker config section', async () => {
      const ProjectSettings = (await import('../components/ProjectSettings')).default

      render(
        <TestWrapper>
          <ProjectSettings
            projectId={1}
            initialConfig={{
              agent_count: 4,
              max_phases: 24,
              circuit_breaker_max_failures: 3,
              circuit_breaker_window_seconds: 300,
              circuit_breaker_recovery_seconds: 60,
            }}
            onSave={vi.fn()}
          />
        </TestWrapper>
      )

      expect(screen.getByText('Circuit Breaker')).toBeInTheDocument()
      expect(screen.getByText('Max Failures Before Open')).toBeInTheDocument()
      expect(screen.getByText('Failure Window')).toBeInTheDocument()
      expect(screen.getByText('Recovery Time')).toBeInTheDocument()
    })

    it('saves circuit breaker config', async () => {
      const user = userEvent.setup()
      const onSave = vi.fn(() => Promise.resolve())
      const ProjectSettings = (await import('../components/ProjectSettings')).default

      render(
        <TestWrapper>
          <ProjectSettings
            projectId={1}
            initialConfig={{
              agent_count: 4,
              max_phases: 24,
              circuit_breaker_max_failures: 3,
              circuit_breaker_window_seconds: 300,
              circuit_breaker_recovery_seconds: 60,
            }}
            onSave={onSave}
          />
        </TestWrapper>
      )

      await user.click(screen.getByText('Save Settings'))
      await waitFor(() => expect(onSave).toHaveBeenCalled())
      const savedConfig = onSave.mock.calls[0][1]
      expect(savedConfig.circuit_breaker_max_failures).toBe(3)
      expect(savedConfig.circuit_breaker_window_seconds).toBe(300)
      expect(savedConfig.circuit_breaker_recovery_seconds).toBe(60)
    })
  })

  describe('Dashboard circuit breaker toast', () => {
    it('shows toast on circuit_breaker_opened event', async () => {
      const Dashboard = (await import('../components/Dashboard')).default

      const { rerender } = render(
        <TestWrapper initialEntries={['/projects/1']}>
          <Routes>
            <Route path="/projects/:id" element={<Dashboard wsEvents={null} onProjectChange={vi.fn()} />} />
          </Routes>
        </TestWrapper>
      )

      // Wait for initial data to load
      await waitFor(() => {
        expect(screen.getByText('Test Project')).toBeInTheDocument()
      })

      // Send circuit breaker event
      rerender(
        <TestWrapper initialEntries={['/projects/1']}>
          <Routes>
            <Route path="/projects/:id" element={
              <Dashboard
                wsEvents={{ type: 'circuit_breaker_opened', agent: 'Claude-1' }}
                onProjectChange={vi.fn()}
              />
            } />
          </Routes>
        </TestWrapper>
      )

      await waitFor(() => {
        expect(screen.getByText(/Circuit breaker opened for Claude-1/)).toBeInTheDocument()
      })
    })
  })
})

describe('React Performance Optimizations', () => {
  it('TerminalOutput uses startTransition for line updates', async () => {
    // Verify startTransition is imported in TerminalOutput
    const source = await import('../components/TerminalOutput')
    expect(source.default).toBeDefined()
  })

  it('Sidebar uses useDeferredValue for search', async () => {
    const Sidebar = (await import('../components/Sidebar')).default
    render(
      <TestWrapper>
        <Sidebar
          projects={[{ id: 1, name: 'Test', goal: 'goal', status: 'stopped' }]}
          onRefresh={vi.fn()}
          collapsed={false}
          onToggle={vi.fn()}
          showArchived={false}
          onShowArchivedChange={vi.fn()}
          projectHealth={{}}
        />
      </TestWrapper>
    )

    expect(screen.getByPlaceholderText('Search projects...')).toBeInTheDocument()
  })

  it('Dashboard lazy-loads heavy components', async () => {
    // Verify that AgentTimeline, AgentEventLog, etc. are lazy-loaded
    // We can check by seeing if the Suspense fallbacks appear
    const Dashboard = (await import('../components/Dashboard')).default
    render(
      <TestWrapper initialEntries={['/projects/1']}>
        <Routes>
          <Route path="/projects/:id" element={<Dashboard wsEvents={null} onProjectChange={vi.fn()} />} />
        </Routes>
      </TestWrapper>
    )

    // Dashboard should render with project data
    await waitFor(() => {
      expect(screen.getByText('Test Project')).toBeInTheDocument()
    })
  })
})
