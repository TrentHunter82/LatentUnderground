/**
 * Phase 16 - Responsive Breakpoint Tests
 * Tests that components respond correctly to different viewport widths.
 * Since jsdom doesn't support CSS media queries, we test:
 * 1. Tailwind responsive classes are present in the DOM
 * 2. Components render without errors at conceptual breakpoints
 * 3. matchMedia-driven behavior (theme, sidebar collapse)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

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
    status: 'running', agents: ['Claude-1', 'Claude-2'],
    signals: {}, tasks: { total: 10, done: 5, percent: 50 }, phase: null,
  })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], total: 0, offset: 0, has_more: false })),
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
  getProjectQuota: vi.fn(() => Promise.resolve({ project_id: 1, quota: {}, usage: {} })),
  getProjectHealth: vi.fn(() => Promise.resolve({ project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable', run_count: 0 })),
  getHealthTrends: vi.fn(() => Promise.resolve({ projects: [], computed_at: new Date().toISOString() })),
  getRunCheckpoints: vi.fn(() => Promise.resolve({ run_id: 1, checkpoints: [], total: 0 })),
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
  useProjects: () => ({ data: [{ id: 1, name: 'Test Project', status: 'running', goal: 'Test', created_at: '2025-01-01' }], isLoading: false, error: null }),
  useProject: () => ({ data: { id: 1, name: 'Test Project', status: 'running', goal: 'Test', type: 'feature', stack: 'python', complexity: 'medium', config: '{"agent_count": 4, "max_phases": 10}', created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00' }, isLoading: false, error: null }),
  useProjectStats: () => ({ data: { total_runs: 5, avg_duration_seconds: 120, total_tasks_completed: 50 }, isLoading: false, error: null }),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useSwarmStatus: () => ({ data: { status: 'running', agents: ['Claude-1', 'Claude-2'], signals: {}, tasks: { total: 10, done: 5, percent: 50 }, phase: null }, isLoading: false, error: null }),
  useSwarmAgents: () => ({ data: { agents: [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 }, { name: 'Claude-2', pid: 1235, alive: true, exit_code: null, output_lines: 5 }] }, isLoading: false, error: null }),
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

describe('Phase 16 - Responsive Breakpoint Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  describe('Dashboard responsive layout', () => {
    it('renders dashboard grid with responsive classes', async () => {
      const { default: Dashboard } = await import('../components/Dashboard')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <Dashboard project={{ id: 1, name: 'Test', status: 'running', goal: 'Goal', config: '{}' }} />
        )
        container = result.container
      })

      // Dashboard should use responsive grid classes
      const gridElements = container.querySelectorAll('[class*="md:grid-cols"]')
      expect(gridElements.length).toBeGreaterThan(0)
    })

    it('header uses responsive padding and text sizes', async () => {
      const { default: Dashboard } = await import('../components/Dashboard')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <Dashboard project={{ id: 1, name: 'Test', status: 'running', goal: 'Goal', config: '{}' }} />
        )
        container = result.container
      })

      // Check for sm: responsive classes in container
      const html = container.innerHTML
      expect(html).toMatch(/sm:/)
    })
  })

  describe('AgentGrid responsive layout', () => {
    it('renders 2-column grid on all sizes', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
        { name: 'Claude-2', pid: 1235, alive: true, exit_code: null, output_lines: 5 },
        { name: 'Claude-3', pid: 1236, alive: false, exit_code: 0, output_lines: 3 },
        { name: 'Claude-4', pid: 1237, alive: false, exit_code: 1, output_lines: 0 },
      ]
      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} />)
        container = result.container
      })

      // Grid should be at least 2 columns
      const grid = container.querySelector('[class*="grid-cols-2"]')
      expect(grid).toBeTruthy()
    })

    it('PID is hidden on mobile via responsive class', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
      ]
      const processAgents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null },
      ]
      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} />)
        container = result.container
      })

      // PID display should have "hidden sm:inline" pattern
      const hiddenElements = container.querySelectorAll('[class*="hidden"][class*="sm:inline"]')
      expect(hiddenElements.length).toBeGreaterThan(0)
    })

    it('uses responsive text sizing', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
      ]
      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} />)
        container = result.container
      })

      const html = container.innerHTML
      // Should have responsive text classes
      expect(html).toMatch(/sm:text-/)
    })
  })

  describe('SwarmControls responsive layout', () => {
    it('buttons use responsive padding', async () => {
      const { default: SwarmControls } = await import('../components/SwarmControls')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <SwarmControls projectId={1} status="created" onStatusChange={vi.fn()} />
        )
        container = result.container
      })

      const html = container.innerHTML
      expect(html).toMatch(/sm:px-/)
    })
  })

  describe('TerminalOutput responsive layout', () => {
    it('terminal has responsive height constraints', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <TerminalOutput projectId={1} status="running" />
        )
        container = result.container
      })

      const html = container.innerHTML
      // Should have responsive max-height
      expect(html).toMatch(/sm:max-h-/)
    })

    it('input bar uses responsive text and padding', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')
      let container
      await act(async () => {
        const result = renderWithProviders(
          <TerminalOutput projectId={1} status="running" />
        )
        container = result.container
      })

      const html = container.innerHTML
      expect(html).toMatch(/sm:py-|sm:px-/)
    })
  })

  describe('NewProject responsive layout', () => {
    it('form fields use responsive grid', async () => {
      const { default: NewProject } = await import('../components/NewProject')
      let container
      await act(async () => {
        const result = renderWithProviders(<NewProject />)
        container = result.container
      })

      // Form should have responsive grid for field layout
      const html = container.innerHTML
      expect(html).toMatch(/sm:grid-cols-2|md:grid-cols-2/)
    })

    it('action buttons switch between column and row layout', async () => {
      const { default: NewProject } = await import('../components/NewProject')
      let container
      await act(async () => {
        const result = renderWithProviders(<NewProject />)
        container = result.container
      })

      const html = container.innerHTML
      // Buttons should stack on mobile and row on desktop
      expect(html).toMatch(/flex-col.*sm:flex-row|sm:flex-row/)
    })
  })

  describe('ProjectView responsive tabs', () => {
    it('tabs use responsive text sizing', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')
      let container
      await act(async () => {
        const result = renderWithProviders(<ProjectView />, { route: '/projects/1' })
        container = result.container
      })

      const tablist = screen.getByRole('tablist')
      const html = tablist.innerHTML
      expect(html).toMatch(/sm:text-/)
    })

    it('renders all tabs without overflow', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')
      await act(async () => {
        renderWithProviders(<ProjectView />, { route: '/projects/1' })
      })

      const tabs = screen.getAllByRole('tab')
      expect(tabs.length).toBeGreaterThanOrEqual(5)

      // All tabs should be visible (not hidden)
      for (const tab of tabs) {
        expect(tab).toBeVisible()
      }
    })
  })

  describe('Theme-based responsive behavior', () => {
    it('matchMedia mock provides consistent theme defaults', () => {
      // Verify setup.js matchMedia mock works
      const mql = window.matchMedia('(prefers-color-scheme: dark)')
      expect(mql).toBeTruthy()
      expect(mql.media).toBe('(prefers-color-scheme: dark)')
      expect(typeof mql.addEventListener).toBe('function')
      expect(typeof mql.removeEventListener).toBe('function')
    })

    it('matchMedia mock has complete API surface', () => {
      const mql = window.matchMedia('(min-width: 768px)')
      expect(mql).toHaveProperty('matches')
      expect(mql).toHaveProperty('media')
      expect(mql).toHaveProperty('addEventListener')
      expect(mql).toHaveProperty('removeEventListener')
      expect(mql).toHaveProperty('addListener')
      expect(mql).toHaveProperty('removeListener')
    })
  })
})
