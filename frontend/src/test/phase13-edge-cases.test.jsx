/**
 * Phase 13 - Edge Case Tests
 * Tests for reconnection banner, Dashboard error retry, and memo'd components.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { TestQueryWrapper, createProjectQueryMock, createSwarmQueryMock, createMutationsMock, createApiMock } from './test-utils'

// --- Reconnection Banner Tests ---
// Uses vi.doMock + dynamic imports to control useWebSocket return value
describe('WebSocket Reconnection Banner', () => {
  beforeEach(() => {
    vi.resetModules()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  async function setupAndRender(wsState) {
    vi.doMock('../hooks/useWebSocket', () => ({
      useWebSocket: () => ({ send: vi.fn(), ...wsState }),
    }))
    vi.doMock('../hooks/useHealthCheck', () => ({
      useHealthCheck: () => ({ status: wsState.connected ? 'healthy' : 'error', latency: wsState.connected ? 10 : null }),
    }))
    vi.doMock('../hooks/useNotifications', () => ({
      useNotifications: () => ({ permission: 'default', enabled: false, setEnabled: vi.fn(), requestPermission: vi.fn(), notify: vi.fn() }),
    }))
    vi.doMock('../lib/api', () => ({
      getProjects: vi.fn(() => Promise.resolve([])),
      getProjectsWithArchived: vi.fn(() => Promise.resolve([])),
    }))

    // Dynamic import AFTER mocks are set
    const { default: App } = await import('../App')
    const { ToastProvider } = await import('../components/Toast')
    const { ThemeProvider } = await import('../hooks/useTheme')

    const { TestQueryWrapper: DynTestQueryWrapper } = await import('./test-utils')

    return render(
      <DynTestQueryWrapper>
        <ThemeProvider>
          <MemoryRouter initialEntries={['/']}>
            <ToastProvider>
              <App />
            </ToastProvider>
          </MemoryRouter>
        </ThemeProvider>
      </DynTestQueryWrapper>,
    )
  }

  it('shows reconnecting banner when WebSocket is reconnecting', async () => {
    await setupAndRender({ connected: false, reconnecting: true })

    await waitFor(() => {
      expect(screen.getByText('Reconnecting to server...')).toBeInTheDocument()
    })

    // Banner should have correct ARIA attributes for screen readers
    const banner = screen.getByRole('status')
    expect(banner).toHaveAttribute('aria-live', 'polite')
  })

  it('does NOT show reconnecting banner when connected', async () => {
    await setupAndRender({ connected: true, reconnecting: false })

    await act(async () => { await new Promise(r => setTimeout(r, 50)) })
    expect(screen.queryByText('Reconnecting to server...')).not.toBeInTheDocument()
  })

  it('shows OFFLINE status when disconnected and not reconnecting', async () => {
    await setupAndRender({ connected: false, reconnecting: false })

    await waitFor(() => {
      expect(screen.getByText('OFFLINE')).toBeInTheDocument()
    })
  })
})

// --- Dashboard Error + Retry Tests ---
// These tests need real TanStack Query hooks (not mocked) so that
// getProject.mockRejectedValue() etc. propagate through useProject() -> error state.
// TestQueryWrapper provides QueryClient with retry:false for fast error propagation.

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ id: '1' }),
  }
})

vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getProjects: vi.fn(() => Promise.resolve([])),
  getProjectsWithArchived: vi.fn(() => Promise.resolve([])),
  getProject: vi.fn(),
  getSwarmStatus: vi.fn(),
  getSwarmHistory: vi.fn(),
  getProjectStats: vi.fn(),
  deleteProject: vi.fn(),
  archiveProject: vi.fn(),
  unarchiveProject: vi.fn(),
  startWatch: vi.fn(),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ results: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '' })),
  putFile: vi.fn(),
  getTemplates: vi.fn(() => Promise.resolve([])),
  getWebhooks: vi.fn(() => Promise.resolve([])),
  browseDirectory: vi.fn(() => Promise.resolve({ path: '/', dirs: [] })),
  getStoredApiKey: vi.fn(() => null),
  clearApiKey: vi.fn(),
  setApiKey: vi.fn(),
  getSwarmAgents: vi.fn(() => Promise.resolve({ agents: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], total: 0, offset: 0 })),
  getAgentEvents: vi.fn(() => Promise.resolve({ events: [] })),
  getProjectQuota: vi.fn(() => Promise.resolve({ project_id: 1, quota: {}, usage: {} })),
  getProjectHealth: vi.fn(() => Promise.resolve({ project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable', run_count: 0 })),
  getHealthTrends: vi.fn(() => Promise.resolve({ projects: [], computed_at: new Date().toISOString() })),
  getRunCheckpoints: vi.fn(() => Promise.resolve({ run_id: 1, checkpoints: [], total: 0 })),
}))

vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({ notify: vi.fn(), permission: 'granted', requestPermission: vi.fn() }),
}))

const mockUseProject = vi.fn(() => ({ data: null, isLoading: true, error: null, refetch: vi.fn() }))

vi.mock('../hooks/useProjectQuery', () => ({
  ...createProjectQueryMock({
    useProjects: () => ({ data: [], isLoading: false, error: null }),
  }),
  useProject: (...args) => mockUseProject(...args),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock())

vi.mock('../hooks/useMutations', () => createMutationsMock())

vi.mock('../hooks/useDebounce', () => ({
  useDebounce: (val) => val,
}))

import { ToastProvider } from '../components/Toast'
import Dashboard from '../components/Dashboard'
import { getProject, getSwarmStatus, getSwarmHistory, getProjectStats, startWatch } from '../lib/api'

function renderDashboard(props = {}) {
  return render(
    <TestQueryWrapper>
      <MemoryRouter initialEntries={['/projects/1']}>
        <ToastProvider>
          <Dashboard wsEvents={null} onProjectChange={vi.fn()} {...props} />
        </ToastProvider>
      </MemoryRouter>
    </TestQueryWrapper>,
  )
}

describe('Dashboard Error & Retry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    startWatch.mockResolvedValue()
    // Reset hook mock to default error state for error tests
    mockUseProject.mockReturnValue({ data: null, isLoading: false, error: new Error('Connection refused'), refetch: vi.fn() })
  })

  it('shows error panel with Retry button when project load fails', async () => {
    mockUseProject.mockReturnValue({ data: null, isLoading: false, error: new Error('Connection refused'), refetch: vi.fn() })

    await act(async () => { renderDashboard() })

    await waitFor(() => {
      const errorTexts = screen.getAllByText(/Connection refused|error|Error/i)
      expect(errorTexts.length).toBeGreaterThanOrEqual(1)
    })
    const retryBtns = screen.getAllByText('Retry')
    expect(retryBtns.length).toBeGreaterThanOrEqual(1)
  })

  it('retries loading when Retry button is clicked', async () => {
    const refetchFn = vi.fn()
    mockUseProject.mockReturnValue({ data: null, isLoading: false, error: new Error('Timeout'), refetch: refetchFn })

    await act(async () => { renderDashboard() })

    await waitFor(() => {
      const retryBtns = screen.getAllByText('Retry')
      expect(retryBtns.length).toBeGreaterThanOrEqual(1)
    })

    await act(async () => {
      const retryBtns = screen.getAllByText('Retry')
      fireEvent.click(retryBtns[0])
    })

    // Verify that clicking Retry triggers the refetch function from useProject
    expect(refetchFn).toHaveBeenCalled()
  })

  it('shows skeleton loader when project is loading', async () => {
    mockUseProject.mockReturnValue({ data: null, isLoading: true, error: null, refetch: vi.fn() })

    await act(async () => { renderDashboard() })

    // DashboardSkeleton renders animated pulse placeholders
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders project data when load succeeds', async () => {
    mockUseProject.mockReturnValue({ data: { id: 1, name: 'Working Project', goal: 'Test goal', status: 'stopped', config: '{}' }, isLoading: false, error: null, refetch: vi.fn() })

    await act(async () => { renderDashboard() })

    await waitFor(() => {
      expect(screen.getByText('Working Project')).toBeInTheDocument()
      expect(screen.getByText('Test goal')).toBeInTheDocument()
    })
  })
})
