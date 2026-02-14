/**
 * Phase 16 - Theme Switching & Persistence Tests
 * Tests dark/light/system theme toggle, localStorage persistence, and matchMedia integration.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { createApiMock } from './test-utils'

// Do NOT mock useTheme here — we test the real ThemeProvider

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
  getProject: vi.fn(() => Promise.resolve({
    id: 1, name: 'Test', status: 'created', goal: 'Test', type: 'feature',
    stack: 'python', complexity: 'medium', config: '{}',
    created_at: '2025-01-01T00:00:00', updated_at: '2025-01-01T00:00:00',
  })),
  createProject: vi.fn(() => Promise.resolve({ id: 1 })),
  updateProject: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  getSwarmStatus: vi.fn(() => Promise.resolve({ status: 'created', agents: [], signals: {}, tasks: { total: 0, done: 0, percent: 0 }, phase: null })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], total: 0, offset: 0, has_more: false })),
  getSwarmAgents: vi.fn(() => Promise.resolve({ agents: [] })),
  sendSwarmInput: vi.fn(() => Promise.resolve({})),
  stopSwarmAgent: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched' })),
  stopSwarm: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  getLogs: vi.fn(() => Promise.resolve({ lines: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ lines: [] })),
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

vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 42 }),
}))

// --- Tests ---

describe('Phase 16 - Theme Switching & Persistence', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
    // Reset document classes
    document.documentElement.classList.remove('light')
  })

  describe('ThemeProvider', () => {
    it('defaults to system mode when no stored preference', async () => {
      const { ThemeProvider, useTheme } = await import('../hooks/useTheme')

      let themeState = null
      function ThemeReader() {
        themeState = useTheme()
        return <div data-testid="theme">{themeState.mode}</div>
      }

      render(
        <ThemeProvider>
          <ThemeReader />
        </ThemeProvider>
      )

      expect(themeState.mode).toBe('system')
      // In jsdom, matchMedia returns matches: false for all queries
      // so system mode resolves to 'dark'
      expect(themeState.theme).toBe('dark')
    })

    it('persists dark mode to localStorage', async () => {
      const { ThemeProvider, useTheme } = await import('../hooks/useTheme')

      let themeState = null
      function ThemeReader() {
        themeState = useTheme()
        return <button onClick={themeState.setTheme.bind(null, 'dark')}>Set Dark</button>
      }

      render(
        <ThemeProvider>
          <ThemeReader />
        </ThemeProvider>
      )

      await act(async () => {
        themeState.setTheme('dark')
      })

      expect(localStorage.getItem('latent-theme')).toBe('dark')
    })

    it('persists light mode to localStorage', async () => {
      const { ThemeProvider, useTheme } = await import('../hooks/useTheme')

      let themeState = null
      function ThemeReader() {
        themeState = useTheme()
        return null
      }

      render(
        <ThemeProvider>
          <ThemeReader />
        </ThemeProvider>
      )

      await act(async () => {
        themeState.setTheme('light')
      })

      expect(localStorage.getItem('latent-theme')).toBe('light')
      expect(document.documentElement.classList.contains('light')).toBe(true)
    })

    it('toggleTheme cycles dark → light → system → dark', async () => {
      const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
      localStorage.setItem('latent-theme', 'dark')

      let themeState = null
      function ThemeReader() {
        themeState = useTheme()
        return null
      }

      render(
        <ThemeProvider>
          <ThemeReader />
        </ThemeProvider>
      )

      expect(themeState.mode).toBe('dark')

      // dark → light
      await act(async () => { themeState.toggleTheme() })
      expect(themeState.mode).toBe('light')

      // light → system
      await act(async () => { themeState.toggleTheme() })
      expect(themeState.mode).toBe('system')

      // system → dark
      await act(async () => { themeState.toggleTheme() })
      expect(themeState.mode).toBe('dark')
    })

    it('restores stored preference on mount', async () => {
      localStorage.setItem('latent-theme', 'light')

      // Re-import to get a fresh module
      vi.resetModules()
      const { ThemeProvider, useTheme } = await import('../hooks/useTheme')

      let themeState = null
      function ThemeReader() {
        themeState = useTheme()
        return null
      }

      render(
        <ThemeProvider>
          <ThemeReader />
        </ThemeProvider>
      )

      expect(themeState.mode).toBe('light')
      expect(themeState.theme).toBe('light')
    })

    it('setTheme rejects invalid values', async () => {
      const { ThemeProvider, useTheme } = await import('../hooks/useTheme')

      let themeState = null
      function ThemeReader() {
        themeState = useTheme()
        return null
      }

      render(
        <ThemeProvider>
          <ThemeReader />
        </ThemeProvider>
      )

      const initialMode = themeState.mode

      await act(async () => {
        themeState.setTheme('invalid')
      })

      // Mode should not change for invalid input
      expect(themeState.mode).toBe(initialMode)
    })

    it('light mode adds "light" class to document root', async () => {
      const { ThemeProvider, useTheme } = await import('../hooks/useTheme')

      let themeState = null
      function ThemeReader() {
        themeState = useTheme()
        return null
      }

      render(
        <ThemeProvider>
          <ThemeReader />
        </ThemeProvider>
      )

      await act(async () => {
        themeState.setTheme('light')
      })

      expect(document.documentElement.classList.contains('light')).toBe(true)

      await act(async () => {
        themeState.setTheme('dark')
      })

      expect(document.documentElement.classList.contains('light')).toBe(false)
    })

    it('useTheme throws outside of ThemeProvider', async () => {
      const { useTheme } = await import('../hooks/useTheme')

      function Orphan() {
        useTheme()
        return null
      }

      // Suppress console.error for expected error
      const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
      expect(() => render(<Orphan />)).toThrow('useTheme must be used within ThemeProvider')
      spy.mockRestore()
    })
  })
})
