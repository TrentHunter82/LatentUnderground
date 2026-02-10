/**
 * Phase 13 - Edge Case Tests
 * Tests for reconnection banner, Dashboard error retry, and memo'd components.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

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

    return render(
      <ThemeProvider>
        <MemoryRouter initialEntries={['/']}>
          <ToastProvider>
            <App />
          </ToastProvider>
        </MemoryRouter>
      </ThemeProvider>,
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
vi.mock('../lib/api', () => ({
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
}))

import { ToastProvider } from '../components/Toast'
import Dashboard from '../components/Dashboard'
import { getProject, getSwarmStatus, getSwarmHistory, getProjectStats, startWatch } from '../lib/api'

function renderDashboard(props = {}) {
  return render(
    <MemoryRouter initialEntries={['/projects/1']}>
      <ToastProvider>
        <Dashboard wsEvents={null} onProjectChange={vi.fn()} {...props} />
      </ToastProvider>
    </MemoryRouter>,
  )
}

describe('Dashboard Error & Retry', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    startWatch.mockResolvedValue()
  })

  it('shows error panel with Retry button when project load fails', async () => {
    getProject.mockRejectedValue(new Error('Connection refused'))
    getSwarmStatus.mockRejectedValue(new Error('fail'))
    getSwarmHistory.mockRejectedValue(new Error('fail'))
    getProjectStats.mockRejectedValue(new Error('fail'))

    await act(async () => { renderDashboard() })

    await waitFor(() => {
      // Error text appears in both error panel and toast - use getAllByText
      const errorTexts = screen.getAllByText('Connection refused')
      expect(errorTexts.length).toBeGreaterThanOrEqual(1)
    })
    // Retry button in the error panel (not the toast)
    const retryBtns = screen.getAllByText('Retry')
    expect(retryBtns.length).toBeGreaterThanOrEqual(1)
  })

  it('retries loading when Retry button is clicked', async () => {
    getProject.mockRejectedValueOnce(new Error('Timeout'))
    getSwarmStatus.mockRejectedValue(new Error('fail'))
    getSwarmHistory.mockRejectedValue(new Error('fail'))
    getProjectStats.mockRejectedValue(new Error('fail'))

    await act(async () => { renderDashboard() })

    await waitFor(() => {
      const retryBtns = screen.getAllByText('Retry')
      expect(retryBtns.length).toBeGreaterThanOrEqual(1)
    })

    // Set up success response for retry
    getProject.mockResolvedValue({ id: 1, name: 'Recovered Project', goal: 'Build it', status: 'running', config: '{}' })
    getSwarmStatus.mockResolvedValue({ project_id: 1, status: 'running', agents: [], signals: {}, tasks: { total: 0, done: 0, percent: 0 }, phase: {} })
    getSwarmHistory.mockResolvedValue({ runs: [] })
    getProjectStats.mockResolvedValue({ total_runs: 0 })

    // Click the Retry button in the error panel (first one)
    await act(async () => {
      const retryBtns = screen.getAllByText('Retry')
      fireEvent.click(retryBtns[0])
    })

    await waitFor(() => {
      expect(screen.getByText('Recovered Project')).toBeInTheDocument()
    })
  })

  it('shows skeleton loader when project is loading', async () => {
    // Keep project loading forever
    getProject.mockImplementation(() => new Promise(() => {}))
    getSwarmStatus.mockImplementation(() => new Promise(() => {}))
    getSwarmHistory.mockImplementation(() => new Promise(() => {}))
    getProjectStats.mockImplementation(() => new Promise(() => {}))

    await act(async () => { renderDashboard() })

    // DashboardSkeleton renders animated pulse placeholders
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders project data when load succeeds', async () => {
    getProject.mockResolvedValue({ id: 1, name: 'Working Project', goal: 'Test goal', status: 'stopped', config: '{}' })
    getSwarmStatus.mockResolvedValue({ project_id: 1, status: 'stopped', agents: [], signals: {}, tasks: { total: 5, done: 2, percent: 40 }, phase: {} })
    getSwarmHistory.mockResolvedValue({ runs: [] })
    getProjectStats.mockResolvedValue({ total_runs: 0 })

    await act(async () => { renderDashboard() })

    await waitFor(() => {
      expect(screen.getByText('Working Project')).toBeInTheDocument()
      expect(screen.getByText('Test goal')).toBeInTheDocument()
    })
  })
})
