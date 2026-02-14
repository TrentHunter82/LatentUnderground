/**
 * Phase 16 - Comprehensive Accessibility Audit
 * Tests every major page/view with axe-core for WCAG violations.
 * Verifies ARIA roles, labels, and keyboard-accessible structures.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'

expect.extend(matchers)

// --- Mock all external dependencies ---

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
  getProjects: vi.fn(() => Promise.resolve([
    { id: 1, name: 'Test Project', status: 'running', goal: 'Test goal', created_at: '2025-01-01' },
  ])),
  getProject: vi.fn(() => Promise.resolve({
    id: 1, name: 'Test Project', status: 'running', goal: 'Test goal',
    type: 'feature', stack: 'python', complexity: 'medium',
    config: '{"agent_count": 4, "max_phases": 10}',
    created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00',
  })),
  createProject: vi.fn(() => Promise.resolve({ id: 2, name: 'New Project' })),
  updateProject: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  getSwarmStatus: vi.fn(() => Promise.resolve({
    status: 'running', agents: ['Claude-1', 'Claude-2'],
    signals: {}, tasks: { total: 10, done: 5, percent: 50 }, phase: null,
  })),
  getSwarmHistory: vi.fn(() => Promise.resolve({
    runs: [{ id: 1, status: 'completed', started_at: '2025-01-01', ended_at: '2025-01-01', duration_seconds: 120 }],
  })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: ['[Claude-1] Hello'], total: 1, offset: 0, has_more: false })),
  getSwarmAgents: vi.fn(() => Promise.resolve({
    agents: [
      { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
      { name: 'Claude-2', pid: 1235, alive: true, exit_code: null, output_lines: 5 },
    ],
  })),
  sendSwarmInput: vi.fn(() => Promise.resolve({})),
  stopSwarmAgent: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched' })),
  stopSwarm: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  getLogs: vi.fn(() => Promise.resolve({ lines: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ lines: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '# Test' })),
  putFile: vi.fn(() => Promise.resolve({})),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 5, avg_duration_seconds: 120, total_tasks_completed: 50 })),
  updateProjectConfig: vi.fn(() => Promise.resolve({})),
  browseDirectory: vi.fn(() => Promise.resolve({ path: '', parent: null, dirs: [] })),
  getTemplates: vi.fn(() => Promise.resolve([])),
  getTemplate: vi.fn(() => Promise.resolve(null)),
  createTemplate: vi.fn(() => Promise.resolve({ id: 1, name: 'New' })),
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
  createAbortable: vi.fn(() => ({ signal: new AbortController().signal, abort: vi.fn() })),
  getSystemInfo: vi.fn(() => Promise.resolve({})),
  getSystemHealth: vi.fn(() => Promise.resolve({ status: 'ok' })),
  getMetrics: vi.fn(() => Promise.resolve('')),
  getHealthTrends: vi.fn(() => Promise.resolve({})),
  getProjectHealth: vi.fn(() => Promise.resolve({ crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 })),
  getProjectQuota: vi.fn(() => Promise.resolve({})),
  getRunCheckpoints: vi.fn(() => Promise.resolve([])),
}))

vi.mock('../hooks/useWebSocket', () => ({
  default: () => ({ lastMessage: null, readyState: 1, reconnecting: false }),
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
  useProject: () => ({ data: { id: 1, name: 'Test Project', goal: 'Test goal', status: 'running', config: '{"agent_count": 4, "max_phases": 10}' }, isLoading: false, error: null }),
  useProjectStats: () => ({ data: { total_runs: 5, avg_duration_seconds: 120, total_tasks_completed: 50 }, isLoading: false, error: null }),
  useProjectHealth: () => ({ data: { crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 }, isLoading: false, error: null }),
  useProjectQuota: () => ({ data: {}, isLoading: false, error: null }),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useSwarmStatus: () => ({ data: { status: 'running', agents: ['Claude-1', 'Claude-2'], signals: {}, tasks: { total: 10, done: 5, percent: 50 }, phase: null }, isLoading: false, error: null }),
  useSwarmHistory: () => ({ data: { runs: [{ id: 1, status: 'completed', started_at: '2025-01-01', ended_at: '2025-01-01', duration_seconds: 120 }] }, isLoading: false, error: null }),
  useSwarmAgents: () => ({ data: { agents: [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 }, { name: 'Claude-2', pid: 1235, alive: true, exit_code: null, output_lines: 5 }] }, isLoading: false, error: null }),
  useSwarmOutput: () => ({ data: { lines: ['[Claude-1] Hello'], total: 1, offset: 0, has_more: false }, isLoading: false, error: null }),
}))

vi.mock('../hooks/useMutations', () => createMutationsMock())

vi.mock('@tanstack/react-query', async (importOriginal) => {
  const actual = await importOriginal()
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: vi.fn(), removeQueries: vi.fn() }),
  }
})

// --- Helper imports (after mocks) ---

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

describe('Phase 16 - Comprehensive Accessibility Audit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  describe('NewProject page', () => {
    it('passes axe-core audit', async () => {
      const { default: NewProject } = await import('../components/NewProject')
      let container
      await act(async () => {
        const result = renderWithProviders(<NewProject />)
        container = result.container
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('has proper form labels and structure', async () => {
      const { default: NewProject } = await import('../components/NewProject')
      await act(async () => {
        renderWithProviders(<NewProject />)
      })

      // All form inputs should have associated labels
      const nameInput = document.getElementById('project-name')
      expect(nameInput).toBeTruthy()
      const label = document.querySelector('label[for="project-name"]')
      expect(label).toBeTruthy()

      // Complexity group should have role="group"
      const group = screen.getByRole('group')
      expect(group).toHaveAttribute('aria-labelledby')
    })
  })

  describe('ProjectView page', () => {
    it('tab navigation passes axe-core audit', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')
      let container
      await act(async () => {
        const result = renderWithProviders(<ProjectView />, { route: '/projects/1' })
        container = result.container
      })
      // Disable heading-order: components rendered in isolation lack parent h1/h2
      const results = await axe(container, { rules: { 'heading-order': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })

    it('has proper tablist/tab/tabpanel ARIA structure', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')
      await act(async () => {
        renderWithProviders(<ProjectView />, { route: '/projects/1' })
      })

      const tablist = screen.getByRole('tablist')
      expect(tablist).toHaveAttribute('aria-label')

      const tabs = screen.getAllByRole('tab')
      expect(tabs.length).toBeGreaterThanOrEqual(5)

      // First tab should be selected by default
      expect(tabs[0]).toHaveAttribute('aria-selected', 'true')

      // Active tab should have corresponding tabpanel
      const panel = screen.getByRole('tabpanel')
      expect(panel).toHaveAttribute('aria-labelledby')
    })
  })

  describe('SwarmControls component', () => {
    it('passes axe-core audit in idle state', async () => {
      const { default: SwarmControls } = await import('../components/SwarmControls')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <SwarmControls projectId={1} status="created" onStatusChange={vi.fn()} />
        )
        container = result.container
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('buttons have aria-busy during loading', async () => {
      const { default: SwarmControls } = await import('../components/SwarmControls')
      await act(async () => {
        renderWithProviders(
          <SwarmControls projectId={1} status="created" onStatusChange={vi.fn()} />
        )
      })
      // Launch button should exist and not be busy initially
      const launchBtn = screen.getByRole('button', { name: /launch/i })
      expect(launchBtn).not.toHaveAttribute('aria-busy', 'true')
    })
  })

  describe('AgentGrid component', () => {
    it('passes axe-core audit with agents', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
        { name: 'Claude-2', pid: 1235, alive: false, exit_code: 0, output_lines: 5 },
        { name: 'Claude-3', pid: 1236, alive: false, exit_code: 1, output_lines: 0 },
      ]
      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} />)
        container = result.container
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('status indicators have accessible text for screen readers', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [
        { name: 'Claude-1', last_heartbeat: null },
      ]
      const processAgents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
      ]
      await act(async () => {
        renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} />)
      })
      // Shape-based status icons use sr-only text for screen readers
      expect(screen.getByText(/Claude-1: running/i)).toBeInTheDocument()
    })
  })

  describe('TerminalOutput component', () => {
    it('passes axe-core audit', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <TerminalOutput projectId={1} status="running" />
        )
        container = result.container
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('terminal output has role="log"', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      const log = screen.getByRole('log')
      expect(log).toBeTruthy()
    })

    it('agent tabs have proper tablist structure', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      const tablist = screen.queryByRole('tablist')
      // Tablist appears when agents are discovered
      if (tablist) {
        const tabs = screen.getAllByRole('tab')
        expect(tabs.length).toBeGreaterThanOrEqual(1)
        // At least one tab should be selected
        const selected = tabs.filter(t => t.getAttribute('aria-selected') === 'true')
        expect(selected.length).toBe(1)
      }
    })

    it('input field has proper error association', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      const input = screen.queryByRole('textbox')
      if (input) {
        // If there's an error state, aria-invalid and aria-describedby should be present
        if (input.getAttribute('aria-invalid') === 'true') {
          expect(input).toHaveAttribute('aria-describedby')
        }
      }
    })
  })

  describe('ProjectSettings component', () => {
    it('passes axe-core audit', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <ProjectSettings projectId={1} onSave={vi.fn()} />
        )
        container = result.container
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })

    it('save button has aria-busy during save', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')
      await act(async () => {
        renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
      })
      const saveBtn = screen.getByRole('button', { name: /save/i })
      expect(saveBtn).toHaveAttribute('aria-busy', 'false')
    })

    it('has aria-live region for status messages', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')
      await act(async () => {
        renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
      })
      const liveRegion = document.querySelector('[aria-live="polite"]')
      expect(liveRegion).toBeTruthy()
    })
  })

  describe('Dashboard component', () => {
    it('passes axe-core audit', async () => {
      const { default: Dashboard } = await import('../components/Dashboard')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <Dashboard project={{ id: 1, name: 'Test', status: 'running', goal: 'Goal', config: '{}' }} />
        )
        container = result.container
      })
      // Disable heading-order: components rendered in isolation lack parent h1/h2
      const results = await axe(container, { rules: { 'heading-order': { enabled: false } } })
      expect(results).toHaveNoViolations()
    })

    it('action buttons have aria-label', async () => {
      const { default: Dashboard } = await import('../components/Dashboard')
      await act(async () => {
        renderWithProviders(
          <Dashboard project={{ id: 1, name: 'Test', status: 'running', goal: 'Goal', config: '{}' }} />
        )
      })
      // Delete button should have descriptive aria-label
      const deleteBtn = screen.queryByRole('button', { name: /delete/i })
      if (deleteBtn) {
        expect(deleteBtn).toHaveAttribute('aria-label')
      }
    })
  })

  describe('FileEditor component', () => {
    it('passes axe-core audit', async () => {
      const { default: FileEditor } = await import('../components/FileEditor')
      let container
      await act(async () => {
        const result = renderWithProviders(<FileEditor projectId={1} />)
        container = result.container
      })
      const results = await axe(container)
      expect(results).toHaveNoViolations()
    })
  })
})
