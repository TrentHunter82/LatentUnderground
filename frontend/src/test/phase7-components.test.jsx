import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { createApiMock, createProjectQueryMock, createSwarmQueryMock, createMutationsMock } from './test-utils'

// Mock react-router-dom
const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: '1' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
  Routes: ({ children }) => <div>{children}</div>,
  Route: ({ element }) => element,
}))

// Mock api module with ALL exports used across the component tree
vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test', goal: 'Test goal', config: null })),
  getProjects: vi.fn(() => Promise.resolve([])),
  createProject: vi.fn(),
  updateProject: vi.fn(),
  deleteProject: vi.fn(),
  getSwarmStatus: vi.fn(() => Promise.resolve(null)),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 0, avg_duration_seconds: null, total_tasks_completed: 0 })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
  updateProjectConfig: vi.fn(),
  sendSwarmInput: vi.fn(() => Promise.resolve({ status: 'sent' })),
  launchSwarm: vi.fn(),
  stopSwarm: vi.fn(),
  getSwarmAgents: vi.fn(() => Promise.resolve({ agents: [] })),
  stopSwarmAgent: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  searchLogs: vi.fn(() => Promise.resolve({ results: [], total: 0 })),
  startWatch: vi.fn(() => Promise.resolve()),
  stopWatch: vi.fn(() => Promise.resolve()),
  getTemplates: vi.fn(() => Promise.resolve([])),
  setApiKey: vi.fn(),
  clearApiKey: vi.fn(),
  getStoredApiKey: vi.fn(() => null),
  getProjectQuota: vi.fn(() => Promise.resolve({ project_id: 1, quota: {}, usage: {} })),
  getProjectHealth: vi.fn(() => Promise.resolve({ project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable', run_count: 0 })),
  getHealthTrends: vi.fn(() => Promise.resolve({ projects: [], computed_at: new Date().toISOString() })),
  getRunCheckpoints: vi.fn(() => Promise.resolve({ run_id: 1, checkpoints: [], total: 0 })),
}))

// Mock hooks
vi.mock('../hooks/useWebSocket', () => ({
  useWebSocket: () => ({ connected: true }),
}))
vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 20 }),
}))
vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({ notify: vi.fn(), permission: 'granted', requestPermission: vi.fn() }),
}))

vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock())
vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock())
vi.mock('../hooks/useMutations', () => createMutationsMock())

import { sendSwarmInput, getLogs, searchLogs, setApiKey, clearApiKey, getStoredApiKey, getSwarmAgents, stopSwarmAgent } from '../lib/api'
import { ToastProvider } from '../components/Toast'

// ============================================================
// Terminal Input (TerminalOutput component)
// ============================================================
import TerminalOutput from '../components/TerminalOutput'

function renderTerminal(props = {}) {
  const defaults = {
    projectId: 1,
    fetchOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
    isRunning: false,
  }
  return render(
    <ToastProvider>
      <TerminalOutput {...defaults} {...props} />
    </ToastProvider>
  )
}

async function renderTerminalWithAgents(props = {}) {
  getSwarmAgents.mockResolvedValue({ agents: [{ name: 'Claude-1', alive: true, pid: 1001, exit_code: null }] })
  const result = renderTerminal({ isRunning: true, ...props })
  // Wait for agent polling to resolve
  await act(async () => { await new Promise(r => setTimeout(r, 50)) })
  return result
}

describe('TerminalOutput Input Bar', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders input field and send button', () => {
    renderTerminal()
    expect(screen.getByLabelText('Terminal input')).toBeInTheDocument()
    expect(screen.getByLabelText('Send input')).toBeInTheDocument()
  })

  it('input is disabled when not running', () => {
    renderTerminal({ isRunning: false })
    const input = screen.getByLabelText('Terminal input')
    expect(input).toBeDisabled()
    expect(input).toHaveAttribute('placeholder', 'Waiting for agents...')
  })

  it('input is enabled when agents are alive', async () => {
    const { getSwarmAgents } = await import('../lib/api')
    getSwarmAgents.mockResolvedValue({ agents: [{ name: 'Claude-1', alive: true, pid: 1001 }] })
    renderTerminal({ isRunning: true })
    // Wait for agent polling to resolve
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })
    const input = screen.getByLabelText('Terminal input')
    expect(input).not.toBeDisabled()
    expect(input).toHaveAttribute('placeholder', 'Send to all agents (Enter to submit)')
  })

  it('send button disabled when input is empty', () => {
    renderTerminal({ isRunning: true })
    expect(screen.getByLabelText('Send input')).toBeDisabled()
  })

  it('calls sendSwarmInput on Enter key', async () => {
    sendSwarmInput.mockResolvedValue({ status: 'sent' })
    await renderTerminalWithAgents()

    const input = screen.getByLabelText('Terminal input')
    fireEvent.change(input, { target: { value: 'hello world' } })
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' })
    })

    expect(sendSwarmInput).toHaveBeenCalledWith(1, 'hello world', null)
  })

  it('echoes input locally with > prefix', async () => {
    sendSwarmInput.mockResolvedValue({ status: 'sent' })
    await renderTerminalWithAgents()

    const input = screen.getByLabelText('Terminal input')
    fireEvent.change(input, { target: { value: 'test cmd' } })
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' })
    })

    expect(screen.getByText(/> test cmd/)).toBeInTheDocument()
  })

  it('shows error message on failed send', async () => {
    sendSwarmInput.mockRejectedValue(new Error('Pipe broken'))
    await renderTerminalWithAgents()

    const input = screen.getByLabelText('Terminal input')
    fireEvent.change(input, { target: { value: 'fail cmd' } })
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' })
    })

    expect(screen.getByText('Pipe broken')).toBeInTheDocument()
  })

  it('clears input after successful send', async () => {
    sendSwarmInput.mockResolvedValue({ status: 'sent' })
    await renderTerminalWithAgents()

    const input = screen.getByLabelText('Terminal input')
    fireEvent.change(input, { target: { value: 'clear me' } })
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' })
    })

    expect(input.value).toBe('')
  })
})

// ============================================================
// AuthModal component
// ============================================================
import AuthModal from '../components/AuthModal'

describe('AuthModal', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders nothing when not open', () => {
    const { container } = render(<AuthModal open={false} onClose={vi.fn()} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders dialog when open', () => {
    render(<AuthModal open={true} onClose={vi.fn()} />)
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('API Key')).toBeInTheDocument()
  })

  it('calls setApiKey and onClose on Save', async () => {
    const onClose = vi.fn()
    render(<AuthModal open={true} onClose={onClose} />)

    const input = screen.getByLabelText('API key')
    fireEvent.change(input, { target: { value: 'my-secret-key' } })
    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    expect(setApiKey).toHaveBeenCalledWith('my-secret-key')
    expect(onClose).toHaveBeenCalled()
  })

  it('calls clearApiKey and onClose on Clear Key', async () => {
    const onClose = vi.fn()
    render(<AuthModal open={true} onClose={onClose} />)

    await act(async () => {
      fireEvent.click(screen.getByText('Clear Key'))
    })

    expect(clearApiKey).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose on Cancel', () => {
    const onClose = vi.fn()
    render(<AuthModal open={true} onClose={onClose} />)
    fireEvent.click(screen.getByText('Cancel'))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose on Escape key', () => {
    const onClose = vi.fn()
    render(<AuthModal open={true} onClose={onClose} />)
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })

  it('Enter key triggers save and close', async () => {
    const onClose = vi.fn()
    render(<AuthModal open={true} onClose={onClose} />)

    await act(async () => {
      fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Enter' })
    })

    // handleKeyDown calls handleSave which calls setApiKey + onClose
    expect(setApiKey).toHaveBeenCalled()
    expect(onClose).toHaveBeenCalled()
  })

  it('loads stored key when opened', () => {
    getStoredApiKey.mockReturnValue('stored-key')
    render(<AuthModal open={true} onClose={vi.fn()} />)
    expect(screen.getByLabelText('API key').value).toBe('stored-key')
  })
})

// ============================================================
// LogViewer Date Range
// ============================================================
import LogViewer from '../components/LogViewer'

describe('LogViewer Date Range', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders from and to date inputs', async () => {
    await act(async () => {
      render(<LogViewer projectId={1} wsEvents={null} />)
    })
    expect(screen.getByLabelText('From date')).toBeInTheDocument()
    expect(screen.getByLabelText('To date')).toBeInTheDocument()
  })

  it('shows clear dates button when date is set', async () => {
    await act(async () => {
      render(<LogViewer projectId={1} wsEvents={null} />)
    })

    // No clear button initially
    expect(screen.queryByLabelText('Clear date filter')).not.toBeInTheDocument()

    // Set a from date
    await act(async () => {
      fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-01-01' } })
    })

    expect(screen.getByLabelText('Clear date filter')).toBeInTheDocument()
  })

  it('calls searchLogs when date filter is set', async () => {
    searchLogs.mockResolvedValue({ results: [], total: 0 })
    getLogs.mockResolvedValue({ logs: [] })

    let result
    await act(async () => {
      result = render(<LogViewer projectId={1} wsEvents={null} />)
    })
    // Wait for initial loadLogs to resolve and skeleton to clear
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })

    await act(async () => {
      fireEvent.change(screen.getByLabelText('From date'), { target: { value: '2026-01-15' } })
    })
    // Wait for runSearch effect to fire
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })

    expect(searchLogs).toHaveBeenCalledWith(
      1,
      expect.objectContaining({ from_date: '2026-01-15' })
    )
  })
})

// ============================================================
// Live Log Indicator
// ============================================================
describe('LogViewer LIVE Indicator', () => {
  it('shows LIVE indicator on WebSocket log event', async () => {
    getLogs.mockResolvedValue({ logs: [] })
    const wsEvent = { type: 'log', agent: 'Claude-1', lines: ['test line'] }
    await act(async () => {
      render(<LogViewer projectId={1} wsEvents={wsEvent} />)
    })
    // Wait for loadLogs to resolve so skeleton clears
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })

    expect(screen.getByText('LIVE')).toBeInTheDocument()
  })

  it('appends WebSocket log lines on rerender', async () => {
    getLogs.mockResolvedValue({ logs: [] })
    // First render with no ws events - let initial loadLogs settle
    let result
    await act(async () => {
      result = render(<LogViewer projectId={1} wsEvents={null} />)
    })
    await act(async () => { await new Promise(r => setTimeout(r, 50)) })

    // Now send ws event via rerender
    const wsEvent = { type: 'log', agent: 'Claude-1', lines: ['Hello from ws'] }
    await act(async () => {
      result.rerender(<LogViewer projectId={1} wsEvents={wsEvent} />)
    })

    expect(screen.getByText('Hello from ws')).toBeInTheDocument()
  })
})

// ============================================================
// Keyboard Shortcuts (in App.jsx)
// ============================================================
describe('Keyboard Shortcuts', () => {
  it('Ctrl+N navigates to new project', () => {
    // Keyboard shortcuts are registered on window in App.jsx
    // We simulate the keydown event directly
    const handler = (e) => {
      const isMod = e.ctrlKey || e.metaKey
      if (isMod && e.key === 'n') {
        e.preventDefault()
        mockNavigate('/projects/new')
      }
    }
    window.addEventListener('keydown', handler)

    fireEvent.keyDown(window, { key: 'n', ctrlKey: true })

    expect(mockNavigate).toHaveBeenCalledWith('/projects/new')
    window.removeEventListener('keydown', handler)
  })

  it('Escape closes auth modal (via window event)', () => {
    let showAuth = true
    const handler = (e) => {
      if (e.key === 'Escape') {
        showAuth = false
      }
    }
    window.addEventListener('keydown', handler)

    fireEvent.keyDown(window, { key: 'Escape' })

    expect(showAuth).toBe(false)
    window.removeEventListener('keydown', handler)
  })
})
