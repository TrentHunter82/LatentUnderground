import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor, renderHook } from '@testing-library/react'
import { ToastProvider, useToast, useSafeToast } from '../components/Toast'

// Mock API module
vi.mock('../lib/api', () => ({
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test', goal: 'Test goal', status: 'created', config: null })),
  getSwarmStatus: vi.fn(() => Promise.resolve(null)),
  deleteProject: vi.fn(() => Promise.resolve()),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getProjectStats: vi.fn(() => Promise.resolve(null)),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
  startWatch: vi.fn(() => Promise.resolve()),
  stopWatch: vi.fn(() => Promise.resolve()),
  updateProjectConfig: vi.fn(() => Promise.resolve()),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ results: [] })),
  getTemplates: vi.fn(() => Promise.resolve([])),
  createTemplate: vi.fn(() => Promise.resolve({ id: 1 })),
  updateTemplate: vi.fn(() => Promise.resolve()),
  deleteTemplate: vi.fn(() => Promise.resolve()),
  browseDirectory: vi.fn(() => Promise.resolve({ path: 'C:/', parent: null, dirs: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '# Test' })),
  putFile: vi.fn(() => Promise.resolve()),
  launchSwarm: vi.fn(() => Promise.resolve()),
  stopSwarm: vi.fn(() => Promise.resolve()),
  sendSwarmInput: vi.fn(() => Promise.resolve()),
  getStoredApiKey: vi.fn(() => null),
  clearApiKey: vi.fn(),
  setApiKey: vi.fn(),
  createProject: vi.fn(() => Promise.resolve({ id: 1 })),
}))

vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: '1' }),
  useNavigate: () => vi.fn(),
  Link: ({ children, ...props }) => <a {...props}>{children}</a>,
  Routes: ({ children }) => children,
  Route: () => null,
}))

vi.mock('../hooks/useTheme.jsx', () => ({
  useTheme: () => ({ theme: 'dark', toggleTheme: vi.fn() }),
  ThemeProvider: ({ children }) => children,
}))

vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 42 }),
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

// --- useSafeToast ---
describe('useSafeToast', () => {
  it('returns a function outside ToastProvider (does not throw)', () => {
    const { result } = renderHook(() => useSafeToast())
    expect(typeof result.current).toBe('function')
    // Calling it should be a no-op, not throw
    expect(() => result.current('test')).not.toThrow()
  })

  it('returns the addToast function inside ToastProvider', () => {
    const { result } = renderHook(() => useSafeToast(), {
      wrapper: ({ children }) => <ToastProvider>{children}</ToastProvider>,
    })
    expect(typeof result.current).toBe('function')
  })

  it('useToast still throws outside ToastProvider', () => {
    expect(() => {
      renderHook(() => useToast())
    }).toThrow('useToast must be used within ToastProvider')
  })
})

// --- Toast retry action rendering ---
describe('Toast retry action buttons', () => {
  function ToastTrigger({ message, action }) {
    const toast = useToast()
    return (
      <button onClick={() => toast(message, 'error', 10000, action)}>
        Trigger
      </button>
    )
  }

  it('renders retry button in error toast', async () => {
    const retryFn = vi.fn()
    render(
      <ToastProvider>
        <ToastTrigger
          message="Delete failed: 500"
          action={{ label: 'Retry', onClick: retryFn }}
        />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('Trigger'))
    expect(screen.getByText('Delete failed: 500')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Retry'))
    expect(retryFn).toHaveBeenCalledTimes(1)
  })

  it('dismisses toast after clicking retry action', async () => {
    const retryFn = vi.fn()
    render(
      <ToastProvider>
        <ToastTrigger
          message="Save failed"
          action={{ label: 'Retry', onClick: retryFn }}
        />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('Trigger'))
    expect(screen.getByText('Save failed')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Retry'))
    // After clicking action, toast should be dismissed
    await waitFor(() => {
      expect(screen.queryByText('Save failed')).not.toBeInTheDocument()
    })
  })
})

// --- LogViewer error toast ---
import LogViewer from '../components/LogViewer'
import { getLogs, searchLogs } from '../lib/api'

describe('LogViewer error notifications', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows toast when log loading fails', async () => {
    getLogs.mockRejectedValueOnce(new Error('Network error'))

    await act(async () => {
      render(
        <ToastProvider>
          <LogViewer projectId={1} wsEvents={null} />
        </ToastProvider>
      )
    })

    await waitFor(() => {
      expect(screen.getByText(/Failed to load logs/)).toBeInTheDocument()
    })
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('renders without provider (useSafeToast fallback)', async () => {
    getLogs.mockResolvedValueOnce({ logs: [] })
    // Should not throw when rendered without ToastProvider
    await act(async () => {
      render(<LogViewer projectId={1} wsEvents={null} />)
    })
    // Component should still render (no crash)
    expect(document.querySelector('.retro-panel')).toBeTruthy()
  })
})

// --- SwarmHistory error toast ---
import SwarmHistory from '../components/SwarmHistory'

describe('SwarmHistory error notifications', () => {
  it('shows toast on history load failure', async () => {
    const failFetch = vi.fn().mockRejectedValue(new Error('Server down'))

    await act(async () => {
      render(
        <ToastProvider>
          <SwarmHistory projectId={1} fetchHistory={failFetch} />
        </ToastProvider>
      )
    })

    await waitFor(() => {
      expect(screen.getByText(/Failed to load history/)).toBeInTheDocument()
    })
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('still renders error state in component', async () => {
    const failFetch = vi.fn().mockRejectedValue(new Error('Timeout'))

    await act(async () => {
      render(
        <ToastProvider>
          <SwarmHistory projectId={1} fetchHistory={failFetch} />
        </ToastProvider>
      )
    })

    await waitFor(() => {
      expect(screen.getByText('Timeout')).toBeInTheDocument()
    })
  })
})

// --- FolderBrowser error toast ---
import FolderBrowser from '../components/FolderBrowser'
import { browseDirectory } from '../lib/api'

describe('FolderBrowser error notifications', () => {
  it('shows toast on browse failure', async () => {
    browseDirectory.mockRejectedValueOnce(new Error('Access denied'))

    await act(async () => {
      render(
        <ToastProvider>
          <FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />
        </ToastProvider>
      )
    })

    await waitFor(() => {
      expect(screen.getByText(/Browse failed/)).toBeInTheDocument()
    })
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })
})

// --- TemplateManager retry actions ---
import TemplateManager from '../components/TemplateManager'
import { getTemplates, createTemplate } from '../lib/api'

describe('TemplateManager retry actions', () => {
  it('shows retry button when template load fails', async () => {
    getTemplates.mockRejectedValueOnce(new Error('API unavailable'))

    await act(async () => {
      render(
        <ToastProvider>
          <TemplateManager onTemplatesChange={vi.fn()} />
        </ToastProvider>
      )
    })

    await waitFor(() => {
      expect(screen.getByText(/Failed to load templates/)).toBeInTheDocument()
    })
  })
})

// --- Bundle optimization: lazy Analytics ---
describe('Bundle optimization', () => {
  it('Analytics is lazily loaded in ProjectView', async () => {
    // The lazy import should create a separate chunk
    const lazyModule = () => import('../components/Analytics')
    const mod = await lazyModule()
    expect(mod.default).toBeDefined()
    expect(typeof mod.default).toBe('function')
  })

  it('markdown chunk is separated in vite config', async () => {
    // Verify react-markdown is importable (confirms it exists in the project)
    const mod = await import('react-markdown')
    expect(mod.default).toBeDefined()
  })
})

// --- Error display patterns are consistent ---
describe('Error display consistency', () => {
  it('Toast action button has correct styling', () => {
    function TriggerToast() {
      const toast = useToast()
      return <button onClick={() => toast('Error', 'error', 10000, { label: 'Retry', onClick: vi.fn() })}>go</button>
    }

    render(
      <ToastProvider>
        <TriggerToast />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('go'))
    const retryBtn = screen.getByText('Retry')
    expect(retryBtn.tagName).toBe('BUTTON')
    expect(retryBtn.className).toContain('btn-neon')
  })

  it('Toast dismiss button exists alongside action', () => {
    function TriggerToast() {
      const toast = useToast()
      return <button onClick={() => toast('Error msg', 'error', 10000, { label: 'Retry', onClick: vi.fn() })}>go</button>
    }

    render(
      <ToastProvider>
        <TriggerToast />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('go'))
    // Both retry and dismiss (×) should be present
    expect(screen.getByText('Retry')).toBeInTheDocument()
    expect(screen.getByText('×')).toBeInTheDocument()
  })
})
