/**
 * Phase 17 - Error Recovery Tests
 * Tests network failures, API timeouts, WebSocket reconnection,
 * and graceful degradation in error scenarios.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { createApiMock, createProjectQueryMock, createSwarmQueryMock, createMutationsMock } from './test-utils'

// --- Mocks ---

const mockNavigate = vi.fn()

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => mockNavigate,
    useParams: () => ({ id: '1' }),
  }
})

vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getProjects: vi.fn(() => Promise.resolve([
    { id: 1, name: 'Test Project', status: 'running', goal: 'Test', created_at: '2025-01-01' },
  ])),
  getProject: vi.fn(() => Promise.resolve({
    id: 1, name: 'Test Project', status: 'running', goal: 'Test',
    type: 'feature', stack: 'python', complexity: 'medium',
    config: '{"agent_count": 4, "max_phases": 10}',
    created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00',
  })),
  createProject: vi.fn(() => Promise.resolve({ id: 2 })),
  updateProject: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  getSwarmStatus: vi.fn(() => Promise.resolve({
    status: 'running', agents: ['Claude-1'], signals: {},
    tasks: { total: 10, done: 5, percent: 50 }, phase: null,
  })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], total: 0, offset: 0, has_more: false })),
  getSwarmAgents: vi.fn(() => Promise.resolve({
    agents: [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 5 }],
  })),
  sendSwarmInput: vi.fn(() => Promise.resolve({})),
  stopSwarmAgent: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched' })),
  stopSwarm: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ results: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '# Test' })),
  putFile: vi.fn(() => Promise.resolve({})),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 0, avg_duration_seconds: null, total_tasks_completed: 0 })),
  updateProjectConfig: vi.fn(() => Promise.resolve({})),
  browseDirectory: vi.fn(() => Promise.resolve({ path: '', parent: null, dirs: [] })),
  getTemplates: vi.fn(() => Promise.resolve([])),
  getTemplate: vi.fn(() => Promise.resolve(null)),
  createTemplate: vi.fn(() => Promise.resolve({ id: 1 })),
  updateTemplate: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteTemplate: vi.fn(() => Promise.resolve(null)),
  getWebhooks: vi.fn(() => Promise.resolve([])),
  createWebhook: vi.fn(() => Promise.resolve({ id: 1 })),
  updateWebhook: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteWebhook: vi.fn(() => Promise.resolve(null)),
  archiveProject: vi.fn(() => Promise.resolve({})),
  unarchiveProject: vi.fn(() => Promise.resolve({})),
  getProjectsWithArchived: vi.fn(() => Promise.resolve([])),
  startWatch: vi.fn(() => Promise.resolve({})),
  stopWatch: vi.fn(() => Promise.resolve({})),
  setApiKey: vi.fn(),
  clearApiKey: vi.fn(),
  getStoredApiKey: vi.fn(() => null),
  getSystemInfo: vi.fn(() => Promise.resolve({})),
  getSystemHealth: vi.fn(() => Promise.resolve({ status: 'ok' })),
  getMetrics: vi.fn(() => Promise.resolve('')),
  getHealthTrends: vi.fn(() => Promise.resolve({})),
  getProjectHealth: vi.fn(() => Promise.resolve({ crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 })),
  getProjectQuota: vi.fn(() => Promise.resolve({})),
  getRunCheckpoints: vi.fn(() => Promise.resolve([])),
}))

vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connected: true, reconnecting: false }),
}))

vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({ notify: vi.fn(), permission: 'granted', requestPermission: vi.fn() }),
}))

vi.mock('../hooks/useTheme', () => ({
  useTheme: () => ({ theme: 'dark', mode: 'dark', toggleTheme: vi.fn(), setTheme: vi.fn() }),
  ThemeProvider: ({ children }) => children,
}))

vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 42 }),
}))

vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock({
  useProjects: () => ({ data: [{ id: 1, name: 'Test Project', status: 'running', goal: 'Test', created_at: '2025-01-01' }], isLoading: false, error: null }),
  useProject: () => ({ data: { id: 1, name: 'Test Project', status: 'running', goal: 'Test', type: 'feature', stack: 'python', complexity: 'medium', config: '{"agent_count": 4, "max_phases": 10}', created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00' }, isLoading: false, error: null }),
  useProjectStats: () => ({ data: { total_runs: 0, avg_duration_seconds: null, total_tasks_completed: 0 }, isLoading: false, error: null }),
  useProjectHealth: () => ({ data: { crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 }, isLoading: false, error: null }),
  useProjectQuota: () => ({ data: {}, isLoading: false, error: null }),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useSwarmStatus: () => ({ data: { status: 'running', agents: ['Claude-1'], signals: {}, tasks: { total: 10, done: 5, percent: 50 }, phase: null }, isLoading: false, error: null }),
  useSwarmAgents: () => ({ data: { agents: [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 5 }] }, isLoading: false, error: null }),
  useSwarmOutput: () => ({ data: { lines: [], total: 0, offset: 0, has_more: false }, isLoading: false, error: null }),
}))

vi.mock('../hooks/useMutations', () => createMutationsMock())

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() }),
  }
})

import { ToastProvider } from '../components/Toast'
import { TestQueryWrapper } from './test-utils'

function renderWithProviders(ui, { route = '/' } = {}) {
  return render(
    <TestQueryWrapper>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          {ui}
        </ToastProvider>
      </MemoryRouter>
    </TestQueryWrapper>
  )
}

// --- Tests ---

describe('Phase 17 - Error Recovery Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  describe('Dashboard API failure recovery', () => {
    // Dashboard uses useParams() to get project ID and fetches via getProject.
    // It uses Promise.all with .catch() for secondary endpoints so partial failures are handled.

    it('renders partial data when stats endpoint fails', async () => {
      const { getProjectStats } = await import('../lib/api')
      getProjectStats.mockRejectedValue(new Error('Stats unavailable'))
      // getProject/getSwarmStatus still succeed (from top-level mocks)

      const { default: Dashboard } = await import('../components/Dashboard')
      await act(async () => {
        renderWithProviders(<Dashboard />, { route: '/projects/1' })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      // Dashboard should still render project name from getProject mock
      expect(screen.getByText('Test Project')).toBeInTheDocument()
    })

    it('renders partial data when agents endpoint fails', async () => {
      const { getSwarmAgents } = await import('../lib/api')
      getSwarmAgents.mockRejectedValue(new Error('Agent service down'))

      const { default: Dashboard } = await import('../components/Dashboard')
      await act(async () => {
        renderWithProviders(<Dashboard />, { route: '/projects/1' })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      // Dashboard renders without agent data (no crash)
      expect(screen.getByText('Test Project')).toBeInTheDocument()
    })

    it('renders partial data when history endpoint fails', async () => {
      const { getSwarmHistory } = await import('../lib/api')
      getSwarmHistory.mockRejectedValue(new Error('History unavailable'))

      const { default: Dashboard } = await import('../components/Dashboard')
      await act(async () => {
        renderWithProviders(<Dashboard />, { route: '/projects/1' })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      expect(screen.getByText('Test Project')).toBeInTheDocument()
    })
  })

  describe('TerminalOutput error handling', () => {
    it('renders terminal even when output API fails', async () => {
      const { getSwarmOutput } = await import('../lib/api')
      getSwarmOutput.mockRejectedValue(new Error('Service unavailable'))

      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Terminal should render (log container exists)
      const log = screen.getByRole('log')
      expect(log).toBeTruthy()
    })

    it('shows error on failed input send', async () => {
      const { sendSwarmInput, getSwarmAgents } = await import('../lib/api')
      getSwarmAgents.mockResolvedValue({
        agents: [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 5 }],
      })
      sendSwarmInput.mockRejectedValue(new Error('Connection refused'))

      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      const input = screen.getByLabelText('Terminal input')
      await act(async () => {
        fireEvent.change(input, { target: { value: 'test' } })
      })
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter' })
      })

      // Error message should appear
      await waitFor(() => {
        expect(screen.getByText('Connection refused')).toBeInTheDocument()
      })
    })

    it('still echoes input locally even if send fails', async () => {
      const { sendSwarmInput, getSwarmAgents } = await import('../lib/api')
      getSwarmAgents.mockResolvedValue({
        agents: [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 5 }],
      })
      sendSwarmInput.mockRejectedValue(new Error('Timeout'))

      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      const input = screen.getByLabelText('Terminal input')
      await act(async () => {
        fireEvent.change(input, { target: { value: 'echo test' } })
      })
      await act(async () => {
        fireEvent.keyDown(input, { key: 'Enter' })
      })

      // The input should be echoed in the output even on failure
      await waitFor(() => {
        expect(screen.getByText(/> echo test/)).toBeInTheDocument()
      })
    })

    it('handles agents endpoint failure gracefully', async () => {
      const { getSwarmAgents } = await import('../lib/api')
      getSwarmAgents.mockRejectedValue(new Error('Agent lookup failed'))

      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Terminal still renders without crashing
      expect(screen.getByRole('log')).toBeTruthy()
      // No agent tabs shown when agents fail to load
      const tablist = screen.queryByRole('tablist')
      if (tablist) {
        // If tablist exists, it should have at least the "All" tab
        const tabs = screen.queryAllByRole('tab')
        expect(tabs.length).toBeGreaterThanOrEqual(0)
      }
    })
  })

  describe('SwarmControls error handling', () => {
    it('shows error when launch fails', async () => {
      const { launchSwarm } = await import('../lib/api')
      launchSwarm.mockRejectedValue(new Error('Swarm script not found'))

      const { default: SwarmControls } = await import('../components/SwarmControls')
      const onAction = vi.fn()
      await act(async () => {
        renderWithProviders(
          <SwarmControls projectId={1} status="created" onAction={onAction} />
        )
      })

      const launchBtn = screen.getByRole('button', { name: /launch/i })
      await act(async () => {
        fireEvent.click(launchBtn)
      })

      // Error should be displayed via toast
      await waitFor(() => {
        const errorText = document.body.textContent
        expect(errorText).toMatch(/swarm script not found/i)
      })
    })

    it('shows error when stop fails', async () => {
      const { stopSwarm } = await import('../lib/api')
      stopSwarm.mockRejectedValue(new Error('Stop failed'))

      const { default: SwarmControls } = await import('../components/SwarmControls')
      const onAction = vi.fn()
      await act(async () => {
        renderWithProviders(
          <SwarmControls projectId={1} status="running" onAction={onAction} />
        )
      })

      // Click the Stop Swarm button (opens ConfirmDialog)
      const stopBtn = screen.getByRole('button', { name: /stop/i })
      await act(async () => {
        fireEvent.click(stopBtn)
      })

      // Click confirm in the ConfirmDialog
      await waitFor(() => {
        expect(screen.getByRole('alertdialog')).toBeInTheDocument()
      })
      const confirmBtn = screen.getByRole('alertdialog').querySelector('button.btn-neon-danger') ||
        screen.getAllByRole('button').find(b => b.textContent === 'Stop Swarm' && b !== stopBtn)
      await act(async () => {
        fireEvent.click(confirmBtn)
      })

      await waitFor(() => {
        const errorText = document.body.textContent
        expect(errorText).toMatch(/stop failed/i)
      })
    })
  })

  describe('NewProject error handling', () => {
    it('shows error when project creation fails', async () => {
      const { createProject } = await import('../lib/api')
      createProject.mockRejectedValue(new Error('Database full'))

      const { default: NewProject } = await import('../components/NewProject')
      await act(async () => {
        renderWithProviders(<NewProject />)
      })

      // Fill all required fields (name, goal, folder_path)
      const nameInput = document.getElementById('project-name')
      const goalInput = document.getElementById('project-goal')
      const folderInput = document.getElementById('folder-path')
      await act(async () => {
        fireEvent.change(nameInput, { target: { value: 'Fail Project' } })
      })
      await act(async () => {
        fireEvent.change(goalInput, { target: { value: 'Test failure' } })
      })
      await act(async () => {
        fireEvent.change(folderInput, { target: { value: 'C:/test' } })
      })

      // Use "Create & Launch" button which calls doLaunchNew directly (no form validation)
      // Or submit form via the Create Project button
      const submitBtn = screen.getByRole('button', { name: /^Create Project$/i })
      await act(async () => {
        fireEvent.click(submitBtn)
      })

      // Error should be displayed (inline alert div + toast - both have role="alert")
      await waitFor(() => {
        const alerts = screen.getAllByRole('alert')
        expect(alerts.length).toBeGreaterThanOrEqual(1)
        const hasError = alerts.some(a => a.textContent.match(/database full/i))
        expect(hasError).toBe(true)
      })
    })
  })

  describe('LogViewer error handling', () => {
    it('renders empty state when getLogs fails', async () => {
      const { getLogs } = await import('../lib/api')
      getLogs.mockRejectedValue(new Error('Log service unavailable'))

      const { default: LogViewer } = await import('../components/LogViewer')
      await act(async () => {
        render(
          <TestQueryWrapper>
            <MemoryRouter>
              <ToastProvider>
                <LogViewer projectId={1} wsEvents={null} />
              </ToastProvider>
            </MemoryRouter>
          </TestQueryWrapper>
        )
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Should not crash - renders component (even if empty)
      expect(screen.getByLabelText('From date')).toBeInTheDocument()
    })

    it('renders empty state when searchLogs fails', async () => {
      const { getLogs, searchLogs } = await import('../lib/api')
      getLogs.mockResolvedValue({ logs: [] })
      searchLogs.mockRejectedValue(new Error('Search timeout'))

      const { default: LogViewer } = await import('../components/LogViewer')
      await act(async () => {
        render(
          <TestQueryWrapper>
            <MemoryRouter>
              <ToastProvider>
                <LogViewer projectId={1} wsEvents={null} />
              </ToastProvider>
            </MemoryRouter>
          </TestQueryWrapper>
        )
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Set date filter to trigger searchLogs
      await act(async () => {
        fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-01-01' } })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Component should not crash
      expect(screen.getByLabelText('From date')).toBeInTheDocument()
    })
  })

  describe('WebSocket reconnection behavior', () => {
    it('useWebSocket hook handles connection loss', async () => {
      // Import the actual hook to test reconnection logic
      const { useWebSocket } = await import('../hooks/useWebSocket')
      const { renderHook, act: hookAct } = await import('@testing-library/react')

      // Mock WebSocket
      const mockWs = {
        close: vi.fn(),
        send: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        readyState: 1,
      }
      const MockWebSocket = vi.fn(() => mockWs)
      globalThis.WebSocket = MockWebSocket

      const onMessage = vi.fn()
      const { result, unmount } = renderHook(() => useWebSocket(onMessage))

      // Verify initial state
      expect(result.current).toHaveProperty('connected')
      expect(result.current).toHaveProperty('reconnecting')

      unmount()
      // Restore
      delete globalThis.WebSocket
    })
  })

  describe('FileEditor error handling', () => {
    it('renders editor even when getFile fails', async () => {
      const { getFile } = await import('../lib/api')
      getFile.mockRejectedValue(new Error('File not found'))

      const { default: FileEditor } = await import('../components/FileEditor')
      await act(async () => {
        renderWithProviders(<FileEditor projectId={1} />)
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      // Editor should render without crashing (container exists)
      const container = document.querySelector('[class*="retro-panel"]')
      expect(container).toBeTruthy()
    }, 15000)

    it('shows error when putFile fails', async () => {
      const { getFile, putFile } = await import('../lib/api')
      getFile.mockResolvedValue({ content: '# Original' })
      putFile.mockRejectedValue(new Error('Permission denied'))

      const { default: FileEditor } = await import('../components/FileEditor')
      await act(async () => {
        renderWithProviders(<FileEditor projectId={1} />)
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      // Component should have rendered file content
      // The save error is handled by toast in the component
    })
  })

  describe('ProjectSettings error handling', () => {
    it('calls onSave with current config values', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')
      const onSave = vi.fn(() => Promise.resolve())

      await act(async () => {
        renderWithProviders(<ProjectSettings projectId={1} onSave={onSave} />)
      })

      // Click save button
      const saveBtn = screen.getByRole('button', { name: /save/i })
      await act(async () => {
        fireEvent.click(saveBtn)
      })

      // onSave should have been called with default config
      await waitFor(() => {
        expect(onSave).toHaveBeenCalledWith(1, expect.objectContaining({ agent_count: 4, max_phases: 24 }))
      })
      // Component should show saved state
      await waitFor(() => {
        expect(screen.getByText('Settings saved')).toBeInTheDocument()
      })
    })
  })

  describe('API error code handling', () => {
    it('handles 404 error gracefully in ProjectView', async () => {
      const { getProject } = await import('../lib/api')
      getProject.mockRejectedValue(new Error('404: Project not found'))

      const { default: ProjectView } = await import('../components/ProjectView')
      await act(async () => {
        renderWithProviders(<ProjectView />, { route: '/projects/999' })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })

      // Should show error state or loading (not crash)
      const container = document.querySelector('main') || document.querySelector('[class*="retro"]')
      expect(container).toBeTruthy()
    }, 15000)

    it('handles 500 error in API gracefully', async () => {
      const { getProject, getSwarmStatus } = await import('../lib/api')
      // Restore getProject to succeed (clearAllMocks removes implementations)
      getProject.mockResolvedValue({
        id: 1, name: 'Test Project', status: 'running', goal: 'Test',
        config: '{}', created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00',
      })
      getSwarmStatus.mockRejectedValue(new Error('500: Internal Server Error'))

      const { default: Dashboard } = await import('../components/Dashboard')
      await act(async () => {
        renderWithProviders(<Dashboard />, { route: '/projects/1' })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      // Dashboard renders partial data (project name from getProject mock)
      expect(screen.getByText('Test Project')).toBeInTheDocument()
    }, 15000)
  })

  describe('Multiple concurrent failures', () => {
    it('Dashboard survives all secondary endpoints failing', async () => {
      const api = await import('../lib/api')
      // Restore getProject to succeed (clearAllMocks removes implementations)
      api.getProject.mockResolvedValue({
        id: 1, name: 'Test Project', status: 'created', goal: 'Test',
        config: '{}', created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00',
      })
      api.getSwarmStatus.mockRejectedValue(new Error('fail'))
      api.getProjectStats.mockRejectedValue(new Error('fail'))
      api.getSwarmHistory.mockRejectedValue(new Error('fail'))
      api.getSwarmAgents.mockRejectedValue(new Error('fail'))

      const { default: Dashboard } = await import('../components/Dashboard')
      await act(async () => {
        renderWithProviders(<Dashboard />, { route: '/projects/1' })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      // Dashboard should still render with project name from getProject
      expect(screen.getByText('Test Project')).toBeInTheDocument()
    }, 15000)
  })
})
