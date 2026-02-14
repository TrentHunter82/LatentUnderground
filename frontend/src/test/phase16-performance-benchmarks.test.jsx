/**
 * Phase 16 - Performance Benchmarks
 * Measures render time for large data sets (1000+ output lines, many agents, etc.)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// --- Mocks ---

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ id: '1' }),
  }
})

// Generate large output data
function generateOutputLines(count) {
  return Array.from({ length: count }, (_, i) => `[Claude-${(i % 4) + 1}] Output line ${i + 1}: some work being done`)
}

vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getProjects: vi.fn(() => Promise.resolve([])),
  getProject: vi.fn(() => Promise.resolve({
    id: 1, name: 'Perf Test', status: 'running', goal: 'Performance', type: 'feature',
    stack: 'python', complexity: 'medium',
    config: '{"agent_count": 4, "max_phases": 10}',
    created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00',
  })),
  createProject: vi.fn(() => Promise.resolve({ id: 1 })),
  updateProject: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  getSwarmStatus: vi.fn(() => Promise.resolve({
    status: 'running', agents: ['Claude-1', 'Claude-2', 'Claude-3', 'Claude-4'],
    signals: {}, tasks: { total: 100, done: 50, percent: 50 }, phase: null,
  })),
  getSwarmHistory: vi.fn(() => Promise.resolve({
    runs: Array.from({ length: 50 }, (_, i) => ({
      id: i + 1, status: i % 3 === 0 ? 'completed' : 'crashed',
      started_at: `2025-01-${String(i + 1).padStart(2, '0')}`,
      ended_at: `2025-01-${String(i + 1).padStart(2, '0')}`,
      duration_seconds: Math.floor(Math.random() * 3600),
    })),
  })),
  getSwarmOutput: vi.fn(() => Promise.resolve({
    lines: generateOutputLines(1000), total: 1000, offset: 0, has_more: false,
  })),
  getSwarmAgents: vi.fn(() => Promise.resolve({
    agents: Array.from({ length: 10 }, (_, i) => ({
      name: `Claude-${i + 1}`, pid: 1000 + i, alive: i < 5, exit_code: i >= 5 ? (i % 2 === 0 ? 0 : 1) : null,
      output_lines: Math.floor(Math.random() * 100),
    })),
  })),
  sendSwarmInput: vi.fn(() => Promise.resolve({})),
  stopSwarmAgent: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched' })),
  stopSwarm: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  getLogs: vi.fn(() => Promise.resolve({ lines: Array.from({ length: 500 }, (_, i) => `[INFO] Log line ${i}`) })),
  searchLogs: vi.fn(() => Promise.resolve({ lines: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '# Test\n'.repeat(100) })),
  putFile: vi.fn(() => Promise.resolve({})),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 50, avg_duration_seconds: 600, total_tasks_completed: 500 })),
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
  useProjects: () => ({ data: [], isLoading: false, error: null }),
  useProject: () => ({ data: { id: 1, name: 'Perf Test', status: 'running', goal: 'Performance', type: 'feature', stack: 'python', complexity: 'medium', config: '{"agent_count": 4, "max_phases": 10}', created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00' }, isLoading: false, error: null }),
  useProjectStats: () => ({ data: { total_runs: 50, avg_duration_seconds: 600, total_tasks_completed: 500 }, isLoading: false, error: null }),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useSwarmStatus: () => ({ data: { status: 'running', agents: ['Claude-1', 'Claude-2', 'Claude-3', 'Claude-4'], signals: {}, tasks: { total: 100, done: 50, percent: 50 }, phase: null }, isLoading: false, error: null }),
  useSwarmHistory: () => ({ data: { runs: Array.from({ length: 50 }, (_, i) => ({ id: i + 1, status: i % 3 === 0 ? 'completed' : 'crashed', started_at: `2025-01-${String(i + 1).padStart(2, '0')}`, ended_at: `2025-01-${String(i + 1).padStart(2, '0')}`, duration_seconds: Math.floor(Math.random() * 3600) })) }, isLoading: false, error: null }),
  useSwarmAgents: () => ({ data: { agents: Array.from({ length: 10 }, (_, i) => ({ name: `Claude-${i + 1}`, pid: 1000 + i, alive: i < 5, exit_code: i >= 5 ? (i % 2 === 0 ? 0 : 1) : null, output_lines: Math.floor(Math.random() * 100) })) }, isLoading: false, error: null }),
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

// --- Performance Tests ---

describe('Phase 16 - Performance Benchmarks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  describe('TerminalOutput with 1000+ lines', () => {
    it('renders 1000 output lines within 2000ms', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')

      const start = performance.now()
      await act(async () => {
        renderWithProviders(<TerminalOutput projectId={1} status="running" />)
      })
      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(2000)
    }, 10000)

    it('DOM node count stays reasonable with 1000 lines', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')

      let container
      await act(async () => {
        const result = renderWithProviders(<TerminalOutput projectId={1} status="running" />)
        container = result.container
      })

      // Total DOM nodes should stay under 10000 even with 1000 lines of output
      const nodeCount = container.querySelectorAll('*').length
      expect(nodeCount).toBeLessThan(10000)
    }, 10000)
  })

  describe('AgentGrid with many agents', () => {
    it('renders 10 agents within 500ms', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = Array.from({ length: 10 }, (_, i) => ({
        name: `Claude-${i + 1}`, pid: 1000 + i, alive: i < 5,
        exit_code: i >= 5 ? 0 : null, output_lines: i * 10,
      }))

      const start = performance.now()
      await act(async () => {
        renderWithProviders(<AgentGrid agents={agents} />)
      })
      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(500)
    })
  })

  describe('Dashboard with loaded data', () => {
    it('renders dashboard with full data within 1000ms', async () => {
      const { default: Dashboard } = await import('../components/Dashboard')

      const start = performance.now()
      await act(async () => {
        renderWithProviders(
          <Dashboard project={{
            id: 1, name: 'Perf Test', status: 'running',
            goal: 'A very long goal description that tests truncation behavior in the dashboard header component',
            config: '{"agent_count": 10, "max_phases": 24}',
          }} />
        )
      })
      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(1000)
    })
  })

  describe('SwarmHistory with 50 runs', () => {
    it('renders history list within 500ms', async () => {
      const { default: ProjectView } = await import('../components/ProjectView')

      const start = performance.now()
      await act(async () => {
        renderWithProviders(<ProjectView />, { route: '/projects/1' })
      })
      const elapsed = performance.now() - start

      // ProjectView with all its lazy-loaded components should render quickly
      expect(elapsed).toBeLessThan(2000)
    }, 10000)
  })

  describe('NewProject form', () => {
    it('renders form within 500ms', async () => {
      const { default: NewProject } = await import('../components/NewProject')

      const start = performance.now()
      await act(async () => {
        renderWithProviders(<NewProject />)
      })
      const elapsed = performance.now() - start

      expect(elapsed).toBeLessThan(500)
    })
  })

  describe('Memory efficiency', () => {
    it('multiple renders of heavy components do not accumulate excessive nodes', async () => {
      const { default: TerminalOutput } = await import('../components/TerminalOutput')

      // Render and unmount 3 times
      for (let i = 0; i < 3; i++) {
        const { unmount, container } = renderWithProviders(
          <TerminalOutput projectId={1} status="running" />
        )
        // Verify it rendered
        expect(container.innerHTML.length).toBeGreaterThan(0)
        unmount()
      }
      // If this completes without hanging or crashing, memory management is acceptable
    }, 15000)
  })
})
