import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { TestQueryWrapper, createApiMock } from './test-utils'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: '1' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}))

// Mock api module
vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test', goal: 'Test goal', config: null })),
  getSwarmStatus: vi.fn(() => Promise.resolve(null)),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 3, avg_duration_seconds: 120, total_tasks_completed: 15 })),
  getSwarmHistory: vi.fn(() => Promise.resolve({
    runs: [
      { id: 1, status: 'completed', tasks_completed: 5, duration_seconds: 90 },
      { id: 2, status: 'completed', tasks_completed: 8, duration_seconds: 150 },
      { id: 3, status: 'failed', tasks_completed: 2, duration_seconds: 30 },
    ]
  })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
  updateProjectConfig: vi.fn(),
  deleteProject: vi.fn(),
  startWatch: vi.fn(() => Promise.resolve()),
  launchSwarm: vi.fn(),
  stopSwarm: vi.fn(),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  createProject: vi.fn(),
  getTemplates: vi.fn(() => Promise.resolve([])),
  getProjectQuota: vi.fn(() => Promise.resolve({ project_id: 1, quota: {}, usage: {} })),
  getProjectHealth: vi.fn(() => Promise.resolve({ project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable', run_count: 0 })),
  getHealthTrends: vi.fn(() => Promise.resolve({ projects: [], computed_at: new Date().toISOString() })),
  getRunCheckpoints: vi.fn(() => Promise.resolve({ run_id: 1, checkpoints: [], total: 0 })),
}))

const { createProjectQueryMock, createSwarmQueryMock, createMutationsMock } = await vi.hoisted(() => import('./test-utils'))

vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock({
  useProject: () => ({ data: { id: 1, name: 'Test', goal: 'Test goal', config: null }, isLoading: false, error: null }),
  useProjectStats: () => ({ data: { total_runs: 3, avg_duration_seconds: 120, total_tasks_completed: 15 }, isLoading: false, error: null }),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useSwarmStatus: () => ({ data: null, isLoading: false, error: null }),
  useSwarmHistory: () => ({ data: { runs: [{ id: 1, status: 'completed', tasks_completed: 5, duration_seconds: 90 }, { id: 2, status: 'completed', tasks_completed: 8, duration_seconds: 150 }, { id: 3, status: 'failed', tasks_completed: 2, duration_seconds: 30 }] }, isLoading: false, error: null }),
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

// ============================================================
// Task 5: Health Status Indicator - useHealthCheck
// ============================================================
describe('useHealthCheck', () => {
  let origFetch

  beforeEach(() => {
    vi.useFakeTimers()
    origFetch = global.fetch
    global.fetch = vi.fn()
  })
  afterEach(() => {
    vi.useRealTimers()
    global.fetch = origFetch
  })

  it('returns healthy when API responds fast', async () => {
    vi.resetModules()
    const { useHealthCheck } = await import('../hooks/useHealthCheck')
    global.fetch.mockResolvedValue({ ok: true })

    let result
    function TestComp() {
      result = useHealthCheck()
      return null
    }
    await act(async () => { render(<TestComp />) })

    expect(result.status).toBe('healthy')
    expect(result.latency).toBeTypeOf('number')
  })

  it('returns disconnected when fetch fails', async () => {
    vi.resetModules()
    const { useHealthCheck } = await import('../hooks/useHealthCheck')
    global.fetch.mockRejectedValue(new Error('Network error'))

    let result
    function TestComp() {
      result = useHealthCheck()
      return null
    }
    await act(async () => { render(<TestComp />) })

    expect(result.status).toBe('disconnected')
    expect(result.latency).toBeNull()
  })

  it('returns degraded when response is not ok', async () => {
    vi.resetModules()
    const { useHealthCheck } = await import('../hooks/useHealthCheck')
    global.fetch.mockResolvedValue({ ok: false })

    let result
    function TestComp() {
      result = useHealthCheck()
      return null
    }
    await act(async () => { render(<TestComp />) })

    expect(result.status).toBe('degraded')
  })
})

// ============================================================
// Task 1: Project Search + Status Filter in Sidebar
// ============================================================
import Sidebar from '../components/Sidebar'

function renderSidebar(props = {}) {
  const defaults = {
    projects: [
      { id: 1, name: 'Alpha Project', goal: 'Build alpha', status: 'running' },
      { id: 2, name: 'Beta Project', goal: 'Build beta', status: 'stopped' },
      { id: 3, name: 'Gamma', goal: 'Create gamma system', status: 'created' },
    ],
    onRefresh: vi.fn(),
    collapsed: false,
    onToggle: vi.fn(),
  }
  return render(
    <ToastProvider>
      <Sidebar {...defaults} {...props} />
    </ToastProvider>
  )
}

describe('Sidebar Search', () => {
  it('renders search input', () => {
    renderSidebar()
    expect(screen.getByPlaceholderText('Search projects...')).toBeInTheDocument()
  })

  it('filters projects by name', async () => {
    renderSidebar()
    fireEvent.change(screen.getByPlaceholderText('Search projects...'), { target: { value: 'Alpha' } })
    await waitFor(() => {
      expect(screen.getByText('Alpha Project')).toBeInTheDocument()
      expect(screen.queryByText('Beta Project')).not.toBeInTheDocument()
      expect(screen.queryByText('Gamma')).not.toBeInTheDocument()
    })
  })

  it('filters projects by goal', async () => {
    renderSidebar()
    fireEvent.change(screen.getByPlaceholderText('Search projects...'), { target: { value: 'gamma system' } })
    await waitFor(() => {
      expect(screen.getByText('Gamma')).toBeInTheDocument()
      expect(screen.queryByText('Alpha Project')).not.toBeInTheDocument()
    })
  })

  it('shows empty state when search matches nothing', async () => {
    renderSidebar()
    fireEvent.change(screen.getByPlaceholderText('Search projects...'), { target: { value: 'zzzzz' } })
    await waitFor(() => {
      expect(screen.getByText('No matching projects')).toBeInTheDocument()
    })
  })

  it('search is case-insensitive', async () => {
    renderSidebar()
    fireEvent.change(screen.getByPlaceholderText('Search projects...'), { target: { value: 'alpha' } })
    await waitFor(() => {
      expect(screen.getByText('Alpha Project')).toBeInTheDocument()
    })
  })
})

describe('Sidebar Status Filter', () => {
  it('renders status filter buttons', () => {
    renderSidebar()
    const allButtons = screen.getAllByText('All')
    expect(allButtons.length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('running')).toBeInTheDocument()
    expect(screen.getByText('stopped')).toBeInTheDocument()
    expect(screen.getByText('created')).toBeInTheDocument()
  })

  it('filters by running status', () => {
    renderSidebar()
    fireEvent.click(screen.getByText('running'))
    expect(screen.getByText('Alpha Project')).toBeInTheDocument()
    expect(screen.queryByText('Beta Project')).not.toBeInTheDocument()
    expect(screen.queryByText('Gamma')).not.toBeInTheDocument()
  })

  it('shows all projects when All filter active', () => {
    renderSidebar()
    fireEvent.click(screen.getByText('running'))
    const allButtons = screen.getAllByText('All')
    fireEvent.click(allButtons[0])
    expect(screen.getByText('Alpha Project')).toBeInTheDocument()
    expect(screen.getByText('Beta Project')).toBeInTheDocument()
    expect(screen.getByText('Gamma')).toBeInTheDocument()
  })
})

// ============================================================
// Task 4: Browser Notifications - useNotifications
// ============================================================
describe('useNotifications', () => {
  let origNotification

  beforeEach(() => {
    origNotification = global.Notification
    global.Notification = vi.fn()
    global.Notification.permission = 'granted'
    global.Notification.requestPermission = vi.fn(() => Promise.resolve('granted'))
    localStorage.clear()
  })

  afterEach(() => {
    global.Notification = origNotification
  })

  it('returns permission state', async () => {
    vi.resetModules()
    const { useNotifications } = await import('../hooks/useNotifications')
    let result
    function TestComp() {
      result = useNotifications()
      return null
    }
    render(<TestComp />)
    expect(result.permission).toBe('granted')
  })

  it('requestPermission calls Notification.requestPermission when not yet granted', async () => {
    global.Notification.permission = 'default'
    vi.resetModules()
    const { useNotifications } = await import('../hooks/useNotifications')
    let result
    function TestComp() {
      result = useNotifications()
      return null
    }
    render(<TestComp />)
    await act(async () => { await result.requestPermission() })
    expect(Notification.requestPermission).toHaveBeenCalled()
  })

  it('notify does not fire when tab is focused', async () => {
    localStorage.setItem('latent-notifications-enabled', 'true')
    vi.resetModules()
    const { useNotifications } = await import('../hooks/useNotifications')
    const origHasFocus = document.hasFocus
    document.hasFocus = () => true
    let result
    function TestComp() {
      result = useNotifications()
      return null
    }
    render(<TestComp />)
    result.notify('Test', { body: 'hello' })
    expect(Notification).not.toHaveBeenCalled()
    document.hasFocus = origHasFocus
  })
})

// ============================================================
// Task 3: Log Search Improvements
// ============================================================
import LogViewer from '../components/LogViewer'

describe('LogViewer Search', () => {
  it('renders search input', async () => {
    await act(async () => {
      render(<LogViewer projectId={1} wsEvents={null} />)
    })
    expect(screen.getByPlaceholderText('Search logs...')).toBeInTheDocument()
  })

  it('renders level filter buttons', async () => {
    await act(async () => {
      render(<LogViewer projectId={1} wsEvents={null} />)
    })
    expect(screen.getByText('INFO')).toBeInTheDocument()
    expect(screen.getByText('WARN')).toBeInTheDocument()
    expect(screen.getByText('ERROR')).toBeInTheDocument()
    expect(screen.getByText('DEBUG')).toBeInTheDocument()
  })

  it('renders copy and download buttons', async () => {
    await act(async () => {
      render(<LogViewer projectId={1} wsEvents={null} />)
    })
    expect(screen.getByTitle('Copy logs')).toBeInTheDocument()
    expect(screen.getByTitle('Download logs')).toBeInTheDocument()
  })
})

// ============================================================
// Task 2: Analytics Tab
// ============================================================
import Analytics from '../components/Analytics'
import ProjectView from '../components/ProjectView'
import { getSwarmHistory, getProjectStats } from '../lib/api'

function renderProjectView(props = {}) {
  return render(
    <TestQueryWrapper>
      <ToastProvider>
        <ProjectView wsEvents={null} onProjectChange={vi.fn()} {...props} />
      </ToastProvider>
    </TestQueryWrapper>
  )
}

describe('Analytics Tab in ProjectView', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders Analytics tab button', async () => {
    await act(async () => { renderProjectView() })
    expect(screen.getByRole('tab', { name: 'Analytics' })).toBeInTheDocument()
  })

  it('shows 7 tabs total', async () => {
    await act(async () => { renderProjectView() })
    expect(screen.getAllByRole('tab')).toHaveLength(7)
  })

  it('Settings tab is last (index 6)', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')
    expect(tabs[6]).toHaveTextContent('Settings')
  })
})

describe('Analytics Component', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows empty state when no runs', async () => {
    getSwarmHistory.mockResolvedValue({ runs: [] })
    getProjectStats.mockResolvedValue({ total_runs: 0, avg_duration_seconds: null, total_tasks_completed: 0 })

    await act(async () => { render(<Analytics projectId={1} />) })

    expect(screen.getByText(/Waiting for data/)).toBeInTheDocument()
  })

  it('shows summary chips with stats', async () => {
    getSwarmHistory.mockResolvedValue({
      runs: [
        { id: 1, status: 'completed', tasks_completed: 5, duration_seconds: 90 },
        { id: 2, status: 'completed', tasks_completed: 8, duration_seconds: 150 },
        { id: 3, status: 'failed', tasks_completed: 2, duration_seconds: 30 },
      ]
    })
    getProjectStats.mockResolvedValue({ total_runs: 3, avg_duration_seconds: 120, total_tasks_completed: 15 })

    await act(async () => { render(<Analytics projectId={1} />) })

    // "Total Runs" and "Tasks Done" appear in both summary chips and metric bars
    expect(screen.getAllByText('Total Runs').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Avg Duration')).toBeInTheDocument()
    expect(screen.getAllByText('Tasks Done').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('3').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('15').length).toBeGreaterThanOrEqual(1)
  })

  it('renders SVG charts when data available', async () => {
    getSwarmHistory.mockResolvedValue({
      runs: [
        { id: 1, status: 'completed', tasks_completed: 5, duration_seconds: 90 },
        { id: 2, status: 'completed', tasks_completed: 8, duration_seconds: 150 },
      ]
    })
    getProjectStats.mockResolvedValue({ total_runs: 2, avg_duration_seconds: 120, total_tasks_completed: 13 })

    let container
    await act(async () => {
      const result = render(<Analytics projectId={1} />)
      container = result.container
    })

    const barChart = container.querySelector('svg[aria-label*="Bar chart"]')
    expect(barChart).toBeInTheDocument()
    const timeline = container.querySelector('svg[aria-label="Phase timeline"]')
    expect(timeline).toBeInTheDocument()
  })
})
