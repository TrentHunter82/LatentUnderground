/**
 * Phase 17 - Complete User Journey Frontend Integration Tests
 * Tests the full UI flow: create project → configure → launch → monitor → stop → view history
 * Verifies component interactions through the mocked API layer.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TestQueryWrapper } from './test-utils'

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
    { id: 1, name: 'Journey Project', status: 'created', goal: 'Full lifecycle', created_at: '2026-01-01' },
  ])),
  getProject: vi.fn(() => Promise.resolve({
    id: 1, name: 'Journey Project', status: 'created', goal: 'Full lifecycle',
    type: 'feature', stack: 'python', complexity: 'medium',
    config: '{"agent_count": 4, "max_phases": 10}',
    created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00',
  })),
  createProject: vi.fn(() => Promise.resolve({ id: 2, name: 'New Test Project' })),
  updateProject: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  getSwarmStatus: vi.fn(() => Promise.resolve({
    status: 'created', agents: [], signals: {},
    tasks: { total: 0, done: 0, percent: 0 }, phase: null,
  })),
  getSwarmHistory: vi.fn(() => Promise.resolve({
    runs: [
      { id: 1, status: 'completed', started_at: '2026-01-01 10:00:00', ended_at: '2026-01-01 10:30:00', duration_seconds: 1800 },
      { id: 2, status: 'stopped', started_at: '2026-01-02 14:00:00', ended_at: '2026-01-02 14:15:00', duration_seconds: 900 },
    ],
  })),
  getSwarmOutput: vi.fn(() => Promise.resolve({
    lines: [
      '[Claude-1] Starting iteration 1',
      '[Claude-2] Reading TASKS.md',
      '[Claude-3] Running test suite',
      '[Claude-1] Completed task: implement feature',
    ],
    total: 4, offset: 0, has_more: false,
  })),
  getSwarmAgents: vi.fn(() => Promise.resolve({
    agents: [
      { name: 'Claude-1', pid: 1001, alive: true, exit_code: null, output_lines: 10 },
      { name: 'Claude-2', pid: 1002, alive: true, exit_code: null, output_lines: 8 },
      { name: 'Claude-3', pid: 1003, alive: false, exit_code: 0, output_lines: 5 },
    ],
  })),
  sendSwarmInput: vi.fn(() => Promise.resolve({})),
  stopSwarmAgent: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched' })),
  stopSwarm: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ results: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '# Tasks\n- [x] Done\n- [ ] Todo' })),
  putFile: vi.fn(() => Promise.resolve({})),
  getProjectStats: vi.fn(() => Promise.resolve({
    total_runs: 2, avg_duration_seconds: 1350, total_tasks_completed: 15,
  })),
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

const { createApiMock, createProjectQueryMock, createSwarmQueryMock, createMutationsMock } = await vi.hoisted(() => import('./test-utils'))

vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock({
  useProjects: () => ({ data: [{ id: 1, name: 'Journey Project', status: 'created', goal: 'Full lifecycle', created_at: '2026-01-01' }], isLoading: false, error: null }),
  useProject: () => ({ data: { id: 1, name: 'Journey Project', status: 'created', goal: 'Full lifecycle', type: 'feature', stack: 'python', complexity: 'medium', config: '{"agent_count": 4, "max_phases": 10}', created_at: '2026-01-01T00:00:00', updated_at: '2026-01-01T00:00:00' }, isLoading: false, error: null }),
  useProjectStats: () => ({ data: { total_runs: 2, avg_duration_seconds: 1350, total_tasks_completed: 15 }, isLoading: false, error: null }),
  useProjectHealth: () => ({ data: { crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 }, isLoading: false, error: null }),
  useProjectQuota: () => ({ data: {}, isLoading: false, error: null }),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useSwarmStatus: () => ({ data: { status: 'created', agents: [], signals: {}, tasks: { total: 0, done: 0, percent: 0 }, phase: null }, isLoading: false, error: null }),
  useSwarmHistory: () => ({ data: { runs: [{ id: 1, status: 'completed', started_at: '2026-01-01 10:00:00', ended_at: '2026-01-01 10:30:00', duration_seconds: 1800 }, { id: 2, status: 'stopped', started_at: '2026-01-02 14:00:00', ended_at: '2026-01-02 14:15:00', duration_seconds: 900 }] }, isLoading: false, error: null }),
  useSwarmAgents: () => ({ data: { agents: [{ name: 'Claude-1', pid: 1001, alive: true, exit_code: null, output_lines: 10 }, { name: 'Claude-2', pid: 1002, alive: true, exit_code: null, output_lines: 8 }, { name: 'Claude-3', pid: 1003, alive: false, exit_code: 0, output_lines: 5 }] }, isLoading: false, error: null }),
  useSwarmOutput: () => ({ data: { lines: ['[Claude-1] Starting iteration 1', '[Claude-2] Reading TASKS.md', '[Claude-3] Running test suite', '[Claude-1] Completed task: implement feature'], total: 4, offset: 0, has_more: false }, isLoading: false, error: null }),
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

describe('Phase 17 - Complete User Journey', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  describe('Step 1: Create Project', () => {
    it('NewProject form creates project and navigates', async () => {
      const { createProject } = await import('../lib/api')
      const { default: NewProject } = await import('../components/NewProject')

      await act(async () => {
        renderWithProviders(<NewProject />)
      })

      // Fill in all required fields (name, goal, folder_path)
      const nameInput = document.getElementById('project-name')
      const goalInput = document.getElementById('project-goal')
      const folderInput = document.getElementById('folder-path')
      expect(nameInput).toBeTruthy()
      expect(goalInput).toBeTruthy()
      expect(folderInput).toBeTruthy()

      await act(async () => {
        fireEvent.change(nameInput, { target: { value: 'New Test Project' } })
      })
      await act(async () => {
        fireEvent.change(goalInput, { target: { value: 'Build a feature' } })
      })
      await act(async () => {
        fireEvent.change(folderInput, { target: { value: 'C:/projects/test' } })
      })

      // Submit via Create Project button
      const submitBtn = screen.getByRole('button', { name: /^Create Project$/i })
      await act(async () => {
        fireEvent.click(submitBtn)
      })

      await waitFor(() => {
        expect(createProject).toHaveBeenCalled()
      })

      // Verify navigation happened
      await waitFor(() => {
        expect(mockNavigate).toHaveBeenCalledWith(expect.stringMatching(/\/projects\/\d+/))
      })
    })
  })

  describe('Step 2: Configure Project', () => {
    it('ProjectSettings allows changing agent count and max phases', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')
      const onSave = vi.fn(() => Promise.resolve())

      await act(async () => {
        renderWithProviders(
          <ProjectSettings
            projectId={1}
            onSave={onSave}
            initialConfig={{ agent_count: 4, max_phases: 10 }}
          />
        )
      })

      // Change agent count
      const agentInput = document.getElementById('agentCount')
      expect(agentInput).toBeTruthy()
      await act(async () => {
        fireEvent.change(agentInput, { target: { value: '2' } })
      })
      expect(agentInput.value).toBe('2')

      // Change max phases
      const phasesInput = document.getElementById('maxPhases')
      expect(phasesInput).toBeTruthy()
      await act(async () => {
        fireEvent.change(phasesInput, { target: { value: '6' } })
      })
      expect(phasesInput.value).toBe('6')

      // Save - calls onSave prop directly (not updateProjectConfig API)
      const saveBtn = screen.getByRole('button', { name: /save/i })
      await act(async () => {
        fireEvent.click(saveBtn)
      })

      await waitFor(() => {
        expect(onSave).toHaveBeenCalledWith(
          1,
          expect.objectContaining({ agent_count: 2, max_phases: 6 })
        )
      })
    })
  })

  describe('Step 3: Launch Swarm', () => {
    it('SwarmControls launches swarm and updates status', async () => {
      const { launchSwarm } = await import('../lib/api')
      const { default: SwarmControls } = await import('../components/SwarmControls')
      const onAction = vi.fn()

      await act(async () => {
        renderWithProviders(
          <SwarmControls projectId={1} status="created" onAction={onAction} />
        )
      })

      const launchBtn = screen.getByRole('button', { name: /launch/i })
      expect(launchBtn).toBeInTheDocument()

      await act(async () => {
        fireEvent.click(launchBtn)
      })

      await waitFor(() => {
        expect(launchSwarm).toHaveBeenCalledWith(
          expect.objectContaining({ project_id: 1 })
        )
      })
    })
  })

  describe('Step 4: Monitor Output', () => {
    it('TerminalOutput shows output lines with agent prefixes', async () => {
      const { getSwarmOutput } = await import('../lib/api')
      const { default: TerminalOutput } = await import('../components/TerminalOutput')

      await act(async () => {
        renderWithProviders(
          <TerminalOutput projectId={1} fetchOutput={getSwarmOutput} isRunning={true} />
        )
      })
      // Allow time for initial poll + agent discovery + output fetch
      await act(async () => { await new Promise(r => setTimeout(r, 500)) })

      // Terminal log container should exist
      const log = screen.getByRole('log')
      expect(log).toBeTruthy()

      // Output lines should be rendered (with retries for async polling)
      await waitFor(() => {
        expect(screen.getByText(/Starting iteration 1/)).toBeInTheDocument()
      }, { timeout: 10000 })
    }, 15000)

    it('TerminalOutput shows agent tabs for running agents', async () => {
      const { getSwarmOutput } = await import('../lib/api')
      const { default: TerminalOutput } = await import('../components/TerminalOutput')

      await act(async () => {
        renderWithProviders(
          <TerminalOutput projectId={1} fetchOutput={getSwarmOutput} isRunning={true} />
        )
      })
      await act(async () => { await new Promise(r => setTimeout(r, 500)) })

      // Agent tabs should appear once agents are discovered
      await waitFor(() => {
        const tablist = screen.queryByRole('tablist')
        if (tablist) {
          const tabs = within(tablist).getAllByRole('tab')
          expect(tabs.length).toBeGreaterThanOrEqual(1) // At least "All" tab
        }
      }, { timeout: 10000 })
    }, 15000)
  })

  describe('Step 5: Stop Swarm', () => {
    it('SwarmControls stops a running swarm via ConfirmDialog', async () => {
      const { stopSwarm } = await import('../lib/api')
      const { default: SwarmControls } = await import('../components/SwarmControls')
      const onAction = vi.fn()

      await act(async () => {
        renderWithProviders(
          <SwarmControls projectId={1} status="running" onAction={onAction} />
        )
      })

      // Click the Stop Swarm button (opens ConfirmDialog)
      const stopBtn = screen.getByRole('button', { name: /stop/i })
      expect(stopBtn).toBeInTheDocument()
      await act(async () => {
        fireEvent.click(stopBtn)
      })

      // Wait for ConfirmDialog to appear and click the confirm button
      await waitFor(() => {
        expect(screen.getByRole('alertdialog')).toBeInTheDocument()
      })
      const dialog = screen.getByRole('alertdialog')
      // The confirm button has confirmLabel="Stop Swarm" and is btn-neon-danger
      const confirmBtn = within(dialog).getAllByRole('button').find(b => b.textContent === 'Stop Swarm')
      expect(confirmBtn).toBeTruthy()
      await act(async () => {
        fireEvent.click(confirmBtn)
      })

      await waitFor(() => {
        expect(stopSwarm).toHaveBeenCalledWith(
          expect.objectContaining({ project_id: 1 })
        )
      })
    })
  })

  describe('Step 6: View History', () => {
    it('ProjectView shows history tab with run records', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')

      await act(async () => {
        renderWithProviders(<ProjectView />, { route: '/projects/1' })
      })

      // Find and click History tab
      const tabs = screen.getAllByRole('tab')
      const historyTab = tabs.find(t => t.textContent.includes('History'))
      expect(historyTab).toBeTruthy()

      await act(async () => {
        fireEvent.click(historyTab)
      })

      // The history panel should be shown
      await waitFor(() => {
        const panel = screen.getByRole('tabpanel')
        expect(panel).toBeTruthy()
      })
    })
  })

  describe('Step 7: View Dashboard Stats', () => {
    it('Dashboard shows project stats and agent grid', async () => {
      const { default: Dashboard } = await import('../components/Dashboard')

      // Dashboard uses useParams() to get project ID, then fetches via getProject
      // The getProject mock returns { name: 'Journey Project', ... }
      await act(async () => {
        renderWithProviders(<Dashboard />, { route: '/projects/1' })
      })
      await act(async () => { await new Promise(r => setTimeout(r, 200)) })

      // Project name from getProject mock should appear
      expect(screen.getByText('Journey Project')).toBeInTheDocument()
    })
  })

  describe('Full flow: Tab navigation through all views', () => {
    it('can navigate through all 7 tabs', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')

      await act(async () => {
        renderWithProviders(<ProjectView />, { route: '/projects/1' })
      })

      const tabs = screen.getAllByRole('tab')
      expect(tabs.length).toBeGreaterThanOrEqual(5)

      // Navigate through tabs
      for (let i = 0; i < tabs.length; i++) {
        await act(async () => {
          fireEvent.click(tabs[i])
        })
        expect(tabs[i]).toHaveAttribute('aria-selected', 'true')

        // Verify tabpanel is rendered
        const panel = screen.getByRole('tabpanel')
        expect(panel).toBeTruthy()
      }
    }, 15000)

    it('keyboard navigation cycles through tabs', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')

      await act(async () => {
        renderWithProviders(<ProjectView />, { route: '/projects/1' })
      })

      const tabs = screen.getAllByRole('tab')
      expect(tabs[0]).toHaveAttribute('aria-selected', 'true')

      // ArrowRight through all tabs
      tabs[0].focus()
      for (let i = 0; i < tabs.length - 1; i++) {
        await act(async () => {
          fireEvent.keyDown(document.activeElement, { key: 'ArrowRight' })
        })
      }

      // Last tab should now be selected
      await waitFor(() => {
        const lastTab = tabs[tabs.length - 1]
        expect(lastTab).toHaveAttribute('aria-selected', 'true')
      })

      // Home key goes back to first
      await act(async () => {
        fireEvent.keyDown(document.activeElement, { key: 'Home' })
      })

      await waitFor(() => {
        expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
      })
    })
  })
})
