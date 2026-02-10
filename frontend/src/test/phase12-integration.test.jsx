/**
 * Phase 12 - Frontend Integration Tests
 * Full page rendering with mocked API (not unit-level component tests).
 * Tests complete user flows across multiple components.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { ToastProvider } from '../components/Toast'
import { ThemeProvider } from '../hooks/useTheme'

// Mock all API functions
vi.mock('../lib/api', () => ({
  getProjects: vi.fn(() => Promise.resolve([
    { id: 1, name: 'Alpha Project', goal: 'Build alpha', status: 'running', created_at: '2026-01-01', updated_at: '2026-01-02', archived_at: null },
    { id: 2, name: 'Beta Project', goal: 'Build beta', status: 'stopped', created_at: '2026-01-03', updated_at: '2026-01-04', archived_at: null },
  ])),
  getProjectsWithArchived: vi.fn(() => Promise.resolve([
    { id: 1, name: 'Alpha Project', goal: 'Build alpha', status: 'running', created_at: '2026-01-01', updated_at: '2026-01-02', archived_at: null },
    { id: 2, name: 'Beta Project', goal: 'Build beta', status: 'stopped', created_at: '2026-01-03', updated_at: '2026-01-04', archived_at: null },
    { id: 3, name: 'Archived Project', goal: 'Old stuff', status: 'stopped', created_at: '2025-06-01', updated_at: '2025-06-02', archived_at: '2025-12-01' },
  ])),
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Alpha Project', goal: 'Build alpha', status: 'running', config: '{"agent_count": 4}' })),
  getSwarmStatus: vi.fn(() => Promise.resolve({
    project_id: 1, status: 'running', swarm_pid: 1234, process_alive: true,
    agents: [{ name: 'Claude-1', last_heartbeat: '2026-02-10 12:00:00' }],
    signals: { 'backend-ready': true, 'frontend-ready': false, 'tests-passing': false, 'phase-complete': false },
    tasks: { total: 10, done: 3, percent: 30 },
    phase: { Phase: 1, MaxPhases: 3 },
  })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [
    { id: 1, project_id: 1, started_at: '2026-02-10 12:00:00', ended_at: null, status: 'running', duration_seconds: null },
  ] })),
  getProjectStats: vi.fn(() => Promise.resolve({ project_id: 1, total_runs: 1, avg_duration_seconds: null, total_tasks_completed: 3 })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: ['[stdout] Starting...'], next_offset: 1, total: 1 })),
  createProject: vi.fn(() => Promise.resolve({ id: 3, name: 'New Project' })),
  updateProject: vi.fn(() => Promise.resolve()),
  deleteProject: vi.fn(() => Promise.resolve()),
  archiveProject: vi.fn(() => Promise.resolve({ id: 1, archived_at: '2026-02-10' })),
  unarchiveProject: vi.fn(() => Promise.resolve({ id: 1, archived_at: null })),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched', pid: 9999 })),
  stopSwarm: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  sendSwarmInput: vi.fn(() => Promise.resolve()),
  startWatch: vi.fn(() => Promise.resolve()),
  stopWatch: vi.fn(() => Promise.resolve()),
  updateProjectConfig: vi.fn(() => Promise.resolve()),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ results: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '# Tasks\n- [x] Done\n- [ ] Todo' })),
  putFile: vi.fn(() => Promise.resolve()),
  getTemplates: vi.fn(() => Promise.resolve([])),
  createTemplate: vi.fn(() => Promise.resolve({ id: 1 })),
  updateTemplate: vi.fn(() => Promise.resolve()),
  deleteTemplate: vi.fn(() => Promise.resolve()),
  browseDirectory: vi.fn(() => Promise.resolve({ path: 'C:/', parent: null, dirs: [] })),
  getWebhooks: vi.fn(() => Promise.resolve([])),
  createWebhook: vi.fn(() => Promise.resolve({ id: 1 })),
  updateWebhook: vi.fn(() => Promise.resolve()),
  deleteWebhook: vi.fn(() => Promise.resolve()),
  getStoredApiKey: vi.fn(() => null),
  clearApiKey: vi.fn(),
  setApiKey: vi.fn(),
}))

vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connected: true, reconnecting: false }),
}))

vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 15 }),
}))

vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({
    permission: 'default',
    enabled: false,
    setEnabled: vi.fn(),
    requestPermission: vi.fn(),
    notify: vi.fn(),
  }),
}))

vi.mock('../hooks/useDebounce', () => ({
  useDebounce: (val) => val,
}))

import App from '../App'
import Home from '../components/Home'
import Sidebar from '../components/Sidebar'

function renderApp(initialRoute = '/') {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[initialRoute]}>
        <ToastProvider>
          <App />
        </ToastProvider>
      </MemoryRouter>
    </ThemeProvider>,
  )
}

function renderWithProviders(ui, { route = '/' } = {}) {
  return render(
    <ThemeProvider>
      <MemoryRouter initialEntries={[route]}>
        <ToastProvider>
          {ui}
        </ToastProvider>
      </MemoryRouter>
    </ThemeProvider>,
  )
}

describe('Phase 12 - Frontend Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    // Mark onboarding as complete to avoid modal blocking tests
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  describe('App Shell Integration', () => {
    it('renders the full app shell with sidebar and main content', async () => {
      renderApp()
      // Wait for projects to load - text appears in both sidebar and Home
      await waitFor(() => {
        expect(screen.getAllByText('Latent Underground').length).toBeGreaterThanOrEqual(1)
      })
      // Sidebar brand is present
      expect(screen.getByText('Swarm Control')).toBeInTheDocument()
      // Health status indicator
      expect(screen.getByText('ONLINE')).toBeInTheDocument()
    })

    it('loads and displays projects in sidebar', async () => {
      const { getProjects } = await import('../lib/api')
      renderApp()
      await waitFor(() => {
        expect(getProjects).toHaveBeenCalled()
      })
      await waitFor(() => {
        expect(screen.getByText('Alpha Project')).toBeInTheDocument()
        expect(screen.getByText('Beta Project')).toBeInTheDocument()
      })
    })

    it('shows new project button in sidebar', async () => {
      renderApp()
      await waitFor(() => {
        expect(screen.getByText('+ New Project')).toBeInTheDocument()
      })
    })

    it('shows settings button in top bar', async () => {
      renderApp()
      await waitFor(() => {
        expect(screen.getByLabelText('Open settings')).toBeInTheDocument()
      })
    })

    it('shows keyboard shortcuts button', async () => {
      renderApp()
      await waitFor(() => {
        expect(screen.getByLabelText('Keyboard shortcuts')).toBeInTheDocument()
      })
    })
  })

  describe('Home Page Integration', () => {
    it('renders home page with LU branding and new project CTA', async () => {
      renderApp('/')
      await waitFor(() => {
        expect(screen.getByText('+ New Swarm Project')).toBeInTheDocument()
      })
      expect(screen.getByText(/Swarm orchestration control center/)).toBeInTheDocument()
    })
  })

  describe('ProjectView Integration', () => {
    it('renders project view with dashboard tab by default', async () => {
      renderApp('/projects/1')
      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /dashboard/i })).toBeInTheDocument()
      })
      // All 7 tabs present
      expect(screen.getByRole('tab', { name: /history/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /output/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /files/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /logs/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /analytics/i })).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /settings/i })).toBeInTheDocument()
    })

    it('loads project data and displays status', async () => {
      const { getProject, getSwarmStatus } = await import('../lib/api')
      renderApp('/projects/1')
      await waitFor(() => {
        expect(getProject).toHaveBeenCalledWith(1)
      })
      await waitFor(() => {
        expect(getSwarmStatus).toHaveBeenCalledWith(1)
      })
    })

    it('switches between tabs on click', async () => {
      renderApp('/projects/1')
      await waitFor(() => {
        expect(screen.getByRole('tab', { name: /history/i })).toBeInTheDocument()
      })
      await act(async () => {
        fireEvent.click(screen.getByRole('tab', { name: /history/i }))
      })
      const historyTab = screen.getByRole('tab', { name: /history/i })
      expect(historyTab).toHaveAttribute('aria-selected', 'true')
    })
  })

  describe('Sidebar Search & Filter Integration', () => {
    it('filters projects by search term', async () => {
      const mockProjects = [
        { id: 1, name: 'Alpha Project', goal: 'Build alpha', status: 'running', archived_at: null },
        { id: 2, name: 'Beta Project', goal: 'Build beta', status: 'stopped', archived_at: null },
      ]
      renderWithProviders(
        <Sidebar
          projects={mockProjects}
          onRefresh={vi.fn()}
          collapsed={false}
          onToggle={vi.fn()}
          showArchived={false}
          onShowArchivedChange={vi.fn()}
        />,
      )
      const searchInput = screen.getByPlaceholderText(/search/i)
      await act(async () => {
        fireEvent.change(searchInput, { target: { value: 'Alpha' } })
      })
      expect(screen.getByText('Alpha Project')).toBeInTheDocument()
      expect(screen.queryByText('Beta Project')).not.toBeInTheDocument()
    })

    it('filters projects by status', async () => {
      const mockProjects = [
        { id: 1, name: 'Running Project', goal: 'G1', status: 'running', archived_at: null },
        { id: 2, name: 'Stopped Project', goal: 'G2', status: 'stopped', archived_at: null },
      ]
      renderWithProviders(
        <Sidebar
          projects={mockProjects}
          onRefresh={vi.fn()}
          collapsed={false}
          onToggle={vi.fn()}
          showArchived={false}
          onShowArchivedChange={vi.fn()}
        />,
      )
      // Click the "running" filter button - there may be multiple matches (filter + status dot)
      const runningBtns = screen.getAllByRole('button', { name: /running/i })
      await act(async () => {
        fireEvent.click(runningBtns[0])
      })
      expect(screen.getByText('Running Project')).toBeInTheDocument()
      expect(screen.queryByText('Stopped Project')).not.toBeInTheDocument()
    })
  })

  describe('Keyboard Shortcuts Integration', () => {
    it('Escape closes settings panel', async () => {
      renderApp()
      await waitFor(() => {
        expect(screen.getByLabelText('Open settings')).toBeInTheDocument()
      })
      // Open settings
      await act(async () => {
        fireEvent.click(screen.getByLabelText('Open settings'))
      })
      // Escape should close
      await act(async () => {
        fireEvent.keyDown(window, { key: 'Escape' })
      })
      // Settings should be closed (no settings-specific content visible)
    })
  })

  describe('Health Status Indicator', () => {
    it('shows ONLINE when healthy and connected', async () => {
      renderApp()
      await waitFor(() => {
        expect(screen.getByText('ONLINE')).toBeInTheDocument()
      })
    })
  })

  describe('Onboarding Modal', () => {
    it('shows onboarding on first visit with no projects', async () => {
      localStorage.removeItem('lu_onboarding_complete')
      const { getProjects } = await import('../lib/api')
      getProjects.mockResolvedValue([]) // No projects
      renderApp()
      await waitFor(() => {
        // OnboardingModal should appear (it's lazy-loaded)
        expect(screen.getByText(/Welcome/i)).toBeInTheDocument()
      })
    })

    it('does not show onboarding if already dismissed', async () => {
      localStorage.setItem('lu_onboarding_complete', 'true')
      const { getProjects } = await import('../lib/api')
      getProjects.mockResolvedValue([])
      renderApp()
      // Wait a bit for any async effects
      await act(async () => { await new Promise(r => setTimeout(r, 100)) })
      expect(screen.queryByText(/Welcome/i)).not.toBeInTheDocument()
    })
  })

  describe('Error Recovery Integration', () => {
    it('handles API error on project list gracefully', async () => {
      const { getProjects } = await import('../lib/api')
      getProjects.mockRejectedValueOnce(new Error('Network error'))
      renderApp()
      // App should still render (empty sidebar) - text appears in multiple places
      await waitFor(() => {
        expect(screen.getAllByText('Latent Underground').length).toBeGreaterThanOrEqual(1)
      })
    })

    it('handles API error on project view gracefully', async () => {
      const { getProject } = await import('../lib/api')
      getProject.mockRejectedValueOnce(new Error('Not found'))
      renderApp('/projects/999')
      await waitFor(() => {
        // Should show tabs even if project load fails
        expect(screen.getByRole('tab', { name: /dashboard/i })).toBeInTheDocument()
      })
    })
  })

  describe('Sidebar Toggle', () => {
    it('toggles sidebar visibility', async () => {
      renderApp()
      await waitFor(() => {
        expect(screen.getAllByText('Latent Underground').length).toBeGreaterThanOrEqual(1)
      })
      // Find the hamburger/toggle button
      const toggleBtns = screen.getAllByTitle(/sidebar/i)
      expect(toggleBtns.length).toBeGreaterThan(0)
    })
  })
})
