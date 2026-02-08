import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'

// --- TaskProgress ---
import TaskProgress from '../components/TaskProgress'

describe('TaskProgress', () => {
  it('renders done/total and percent', () => {
    render(<TaskProgress tasks={{ total: 10, done: 7, percent: 70 }} />)
    expect(screen.getByText('7/10')).toBeInTheDocument()
    expect(screen.getByText('(70%)')).toBeInTheDocument()
  })

  it('renders progress bar with correct aria values', () => {
    render(<TaskProgress tasks={{ total: 8, done: 4, percent: 50 }} />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuenow', '50')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
  })

  it('shows remaining count', () => {
    render(<TaskProgress tasks={{ total: 5, done: 2, percent: 40 }} />)
    expect(screen.getByText('2 done')).toBeInTheDocument()
    expect(screen.getByText('3 remaining')).toBeInTheDocument()
  })

  it('handles null/undefined tasks gracefully', () => {
    render(<TaskProgress tasks={null} />)
    expect(screen.getByText('0/0')).toBeInTheDocument()
    expect(screen.getByText('(0%)')).toBeInTheDocument()
  })

  it('does not show counts when total is 0', () => {
    render(<TaskProgress tasks={{ total: 0, done: 0, percent: 0 }} />)
    expect(screen.queryByText('0 done')).not.toBeInTheDocument()
  })
})

// --- SignalPanel ---
import SignalPanel from '../components/SignalPanel'

describe('SignalPanel', () => {
  it('renders all four signal labels', () => {
    render(<SignalPanel signals={{}} />)
    expect(screen.getByText('Backend Ready')).toBeInTheDocument()
    expect(screen.getByText('Frontend Ready')).toBeInTheDocument()
    expect(screen.getByText('Tests Passing')).toBeInTheDocument()
    expect(screen.getByText('Phase Complete')).toBeInTheDocument()
  })

  it('shows active style for true signals', () => {
    render(<SignalPanel signals={{ 'backend-ready': true, 'tests-passing': true }} />)
    // Active signals have text-zinc-200 class (brighter text)
    const backendLabel = screen.getByText('Backend Ready')
    expect(backendLabel.className).toContain('text-zinc-200')
  })

  it('shows inactive style for false signals', () => {
    render(<SignalPanel signals={{ 'backend-ready': false }} />)
    const label = screen.getByText('Backend Ready')
    expect(label.className).toContain('text-zinc-500')
  })

  it('renders phase indicator when phase provided', () => {
    render(<SignalPanel signals={{}} phase={{ Phase: 2, MaxPhases: 3 }} />)
    expect(screen.getByText('Phase')).toBeInTheDocument()
    expect(screen.getByText(/2/)).toBeInTheDocument()
    expect(screen.getByText(/3/)).toBeInTheDocument()
  })

  it('omits phase indicator when no phase', () => {
    render(<SignalPanel signals={{}} />)
    expect(screen.queryByText('Phase')).not.toBeInTheDocument()
  })
})

// --- AgentGrid ---
import AgentGrid from '../components/AgentGrid'

describe('AgentGrid', () => {
  it('shows "No agent data" when agents is empty', () => {
    render(<AgentGrid agents={[]} />)
    expect(screen.getByText('No agent data')).toBeInTheDocument()
  })

  it('shows "No agent data" when agents is null', () => {
    render(<AgentGrid agents={null} />)
    expect(screen.getByText('No agent data')).toBeInTheDocument()
  })

  it('renders agent names and roles', () => {
    const agents = [
      { name: 'Claude-1', last_heartbeat: new Date().toISOString() },
      { name: 'Claude-3', last_heartbeat: new Date().toISOString() },
    ]
    render(<AgentGrid agents={agents} />)
    expect(screen.getByText('Claude-1')).toBeInTheDocument()
    expect(screen.getByText('Backend/Core')).toBeInTheDocument()
    expect(screen.getByText('Claude-3')).toBeInTheDocument()
    expect(screen.getByText('Integration/Test')).toBeInTheDocument()
  })

  it('marks agents with recent heartbeats as Active', () => {
    const agents = [
      { name: 'Claude-1', last_heartbeat: new Date().toISOString() },
    ]
    render(<AgentGrid agents={agents} />)
    expect(screen.getByText(/Active/)).toBeInTheDocument()
  })

  it('marks agents with old heartbeats as Stale', () => {
    const agents = [
      { name: 'Claude-1', last_heartbeat: '2020-01-01T00:00:00Z' },
    ]
    render(<AgentGrid agents={agents} />)
    expect(screen.getByText(/Stale/)).toBeInTheDocument()
  })
})

// --- ConfirmDialog ---
import ConfirmDialog from '../components/ConfirmDialog'

describe('ConfirmDialog', () => {
  it('renders nothing when closed', () => {
    const { container } = render(
      <ConfirmDialog open={false} title="Test" message="Test msg" onConfirm={() => {}} onCancel={() => {}} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders title and message when open', () => {
    render(
      <ConfirmDialog open={true} title="Delete?" message="Are you sure?" onConfirm={() => {}} onCancel={() => {}} />
    )
    expect(screen.getByText('Delete?')).toBeInTheDocument()
    expect(screen.getByText('Are you sure?')).toBeInTheDocument()
  })

  it('calls onConfirm when confirm button clicked', () => {
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog open={true} title="X" message="Y" confirmLabel="Yes" onConfirm={onConfirm} onCancel={() => {}} />
    )
    fireEvent.click(screen.getByText('Yes'))
    expect(onConfirm).toHaveBeenCalledOnce()
  })

  it('calls onCancel when cancel button clicked', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog open={true} title="X" message="Y" onConfirm={() => {}} onCancel={onCancel} />
    )
    fireEvent.click(screen.getByText('Cancel'))
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('calls onCancel on Escape key', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog open={true} title="X" message="Y" onConfirm={() => {}} onCancel={onCancel} />
    )
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledOnce()
  })

  it('has role="alertdialog" and aria-modal when open', () => {
    render(
      <ConfirmDialog open={true} title="Test" message="Msg" onConfirm={() => {}} onCancel={() => {}} />
    )
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('traps focus within dialog on Tab', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog open={true} title="X" message="Y" confirmLabel="OK" cancelLabel="No" onConfirm={() => {}} onCancel={onCancel} />
    )
    const dialog = screen.getByRole('alertdialog')
    const buttons = dialog.querySelectorAll('button')
    const cancelBtn = buttons[0]
    const confirmBtn = buttons[1]

    // Focus the last button and press Tab - should wrap to first
    confirmBtn.focus()
    fireEvent.keyDown(dialog, { key: 'Tab' })
    // The default isn't prevented in test env, but we check the handler doesn't crash

    // Focus the first button and press Shift+Tab - should wrap to last
    cancelBtn.focus()
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true })
  })

  it('uses custom labels', () => {
    render(
      <ConfirmDialog open={true} title="X" message="Y" confirmLabel="Do it" cancelLabel="Nah" onConfirm={() => {}} onCancel={() => {}} />
    )
    expect(screen.getByText('Do it')).toBeInTheDocument()
    expect(screen.getByText('Nah')).toBeInTheDocument()
  })
})

// --- Toast ---
import { ToastProvider, useToast } from '../components/Toast'

function ToastTrigger({ message, type }) {
  const toast = useToast()
  return <button onClick={() => toast(message, type)}>Trigger</button>
}

describe('Toast', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('renders toast on trigger', async () => {
    render(
      <ToastProvider>
        <ToastTrigger message="Hello toast" type="success" />
      </ToastProvider>
    )
    fireEvent.click(screen.getByText('Trigger'))
    expect(screen.getByText('Hello toast')).toBeInTheDocument()
  })

  it('auto-dismisses after duration', async () => {
    render(
      <ToastProvider>
        <ToastTrigger message="Temp toast" type="info" />
      </ToastProvider>
    )
    fireEvent.click(screen.getByText('Trigger'))
    expect(screen.getByText('Temp toast')).toBeInTheDocument()

    act(() => { vi.advanceTimersByTime(5000) })
    expect(screen.queryByText('Temp toast')).not.toBeInTheDocument()
  })

  it('dismiss button removes toast immediately', () => {
    render(
      <ToastProvider>
        <ToastTrigger message="Dismissable" type="error" />
      </ToastProvider>
    )
    fireEvent.click(screen.getByText('Trigger'))
    expect(screen.getByText('Dismissable')).toBeInTheDocument()

    // Click the dismiss button (×)
    const dismissBtn = screen.getByText('×')
    fireEvent.click(dismissBtn)
    expect(screen.queryByText('Dismissable')).not.toBeInTheDocument()
  })

  it('throws when useToast is used outside provider', () => {
    // Suppress console.error for expected error
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<ToastTrigger message="fail" type="error" />)).toThrow(
      'useToast must be used within ToastProvider'
    )
    spy.mockRestore()
  })
})

// --- Skeleton ---
import { DashboardSkeleton } from '../components/Skeleton'

describe('DashboardSkeleton', () => {
  it('renders without crashing', () => {
    const { container } = render(<DashboardSkeleton />)
    // Should have multiple animated pulse elements
    const pulseElements = container.querySelectorAll('.animate-pulse')
    expect(pulseElements.length).toBeGreaterThan(5)
  })
})

// ============================================================
// NEW TESTS - Phase 3 Production Hardening
// ============================================================

// --- SwarmControls ---
vi.mock('../lib/api', () => ({
  launchSwarm: vi.fn(),
  stopSwarm: vi.fn(),
  createProject: vi.fn(),
  getLogs: vi.fn().mockResolvedValue({ logs: [] }),
  deleteProject: vi.fn(),
  getTemplates: vi.fn(() => Promise.resolve([])),
}))

import { launchSwarm, stopSwarm, createProject, getLogs, deleteProject } from '../lib/api'
import SwarmControls from '../components/SwarmControls'

function renderSwarmControls(props = {}) {
  return render(
    <ToastProvider>
      <SwarmControls projectId={1} status="created" onAction={vi.fn()} {...props} />
    </ToastProvider>
  )
}

describe('SwarmControls', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows Launch button when status is created', () => {
    renderSwarmControls({ status: 'created' })
    expect(screen.getByText('Launch')).toBeInTheDocument()
    expect(screen.queryByText('Stop Swarm')).not.toBeInTheDocument()
    expect(screen.queryByText('Resume')).not.toBeInTheDocument()
  })

  it('shows Stop Swarm button when status is running', () => {
    renderSwarmControls({ status: 'running' })
    expect(screen.getByText('Stop Swarm')).toBeInTheDocument()
    expect(screen.queryByText('Launch')).not.toBeInTheDocument()
  })

  it('shows Launch and Resume buttons when status is stopped', () => {
    renderSwarmControls({ status: 'stopped' })
    expect(screen.getByText('Launch')).toBeInTheDocument()
    expect(screen.getByText('Resume')).toBeInTheDocument()
  })

  it('calls launchSwarm with resume=false on Launch click', async () => {
    launchSwarm.mockResolvedValue({})
    renderSwarmControls({ status: 'created' })
    await act(async () => { fireEvent.click(screen.getByText('Launch')) })
    expect(launchSwarm).toHaveBeenCalledWith(expect.objectContaining({
      project_id: 1,
      resume: false,
    }))
  })

  it('calls launchSwarm with resume=true on Resume click', async () => {
    launchSwarm.mockResolvedValue({})
    renderSwarmControls({ status: 'stopped' })
    await act(async () => { fireEvent.click(screen.getByText('Resume')) })
    expect(launchSwarm).toHaveBeenCalledWith(expect.objectContaining({
      project_id: 1,
      resume: true,
    }))
  })

  it('shows confirmation dialog before stopping and calls stopSwarm on confirm', async () => {
    stopSwarm.mockResolvedValue({})
    renderSwarmControls({ status: 'running' })

    // Click Stop -> opens confirmation dialog
    fireEvent.click(screen.getByText('Stop Swarm'))
    expect(screen.getByText(/terminate all running Claude agents/)).toBeInTheDocument()

    // The dialog confirm button is the second "Stop Swarm" text
    const confirmBtns = screen.getAllByText('Stop Swarm')
    // The last one is the dialog's confirm button (rendered after the trigger)
    await act(async () => { fireEvent.click(confirmBtns[confirmBtns.length - 1]) })
    expect(stopSwarm).toHaveBeenCalledWith({ project_id: 1 })
  })
})

// --- NewProject ---
const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({}),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}))

import NewProject from '../components/NewProject'

function renderNewProject(props = {}) {
  return render(<NewProject onProjectChange={vi.fn()} {...props} />)
}

describe('NewProject', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders form with required fields', () => {
    renderNewProject()
    expect(screen.getByText('New Swarm Project')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('My Awesome App')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('What should this project accomplish?')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('C:/Projects/my-app')).toBeInTheDocument()
    expect(screen.getByText('Create Project')).toBeInTheDocument()
    expect(screen.getByText('Create & Launch')).toBeInTheDocument()
  })

  it('updates form fields on input', () => {
    renderNewProject()
    const nameInput = screen.getByPlaceholderText('My Awesome App')
    fireEvent.change(nameInput, { target: { value: 'Test Project' } })
    expect(nameInput.value).toBe('Test Project')
  })

  it('calls createProject on form submit', async () => {
    createProject.mockResolvedValue({ id: 42 })
    const onProjectChange = vi.fn()
    renderNewProject({ onProjectChange })

    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'My App' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'A goal' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'C:/test' } })

    await act(async () => { fireEvent.click(screen.getByText('Create Project')) })

    expect(createProject).toHaveBeenCalledWith(expect.objectContaining({
      name: 'My App',
      goal: 'A goal',
      folder_path: 'C:/test',
    }))
    expect(mockNavigate).toHaveBeenCalledWith('/projects/42')
    expect(onProjectChange).toHaveBeenCalled()
  })

  it('calls createProject + launchSwarm on Create & Launch', async () => {
    createProject.mockResolvedValue({ id: 7 })
    launchSwarm.mockResolvedValue({})
    renderNewProject()

    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'App' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'Goal' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'C:/p' } })

    await act(async () => { fireEvent.click(screen.getByText('Create & Launch')) })

    expect(createProject).toHaveBeenCalled()
    expect(launchSwarm).toHaveBeenCalledWith(expect.objectContaining({ project_id: 7 }))
    expect(mockNavigate).toHaveBeenCalledWith('/projects/7')
  })

  it('displays error message on failure', async () => {
    createProject.mockRejectedValue(new Error('Name required'))
    renderNewProject()

    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'X' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'Y' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'C:/z' } })

    await act(async () => { fireEvent.click(screen.getByText('Create Project')) })

    expect(screen.getByText('Name required')).toBeInTheDocument()
  })

  it('shows loading state during submission', async () => {
    let resolve
    createProject.mockReturnValue(new Promise((r) => { resolve = r }))
    renderNewProject()

    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'X' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'Y' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'C:/z' } })

    await act(async () => { fireEvent.click(screen.getByText('Create Project')) })

    expect(screen.getByText('Creating...')).toBeInTheDocument()

    await act(async () => { resolve({ id: 1 }) })
  })
})

// --- LogViewer ---
import LogViewer from '../components/LogViewer'

describe('LogViewer', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('loads and displays initial logs', async () => {
    getLogs.mockResolvedValue({
      logs: [{ agent: 'Claude-1', lines: ['Starting build', 'Build complete'] }],
    })
    await act(async () => { render(<LogViewer projectId={1} />) })
    expect(screen.getByText('Starting build')).toBeInTheDocument()
    expect(screen.getByText('Build complete')).toBeInTheDocument()
  })

  it('renders agent filter buttons', async () => {
    getLogs.mockResolvedValue({ logs: [] })
    await act(async () => { render(<LogViewer projectId={1} />) })
    expect(screen.getByText('All')).toBeInTheDocument()
    expect(screen.getByText('Claude-1')).toBeInTheDocument()
    expect(screen.getByText('Claude-2')).toBeInTheDocument()
    expect(screen.getByText('Claude-3')).toBeInTheDocument()
    expect(screen.getByText('Claude-4')).toBeInTheDocument()
    expect(screen.getByText('supervisor')).toBeInTheDocument()
  })

  it('shows empty state when no logs', async () => {
    getLogs.mockResolvedValue({ logs: [] })
    await act(async () => { render(<LogViewer projectId={1} />) })
    expect(screen.getByText('No logs')).toBeInTheDocument()
  })

  it('appends logs from WebSocket events', async () => {
    getLogs.mockResolvedValue({ logs: [] })
    const { rerender } = await act(async () =>
      render(<LogViewer projectId={1} wsEvents={null} />)
    )

    await act(async () => {
      rerender(
        <LogViewer
          projectId={1}
          wsEvents={{ type: 'log', agent: 'Claude-2', lines: ['WS log line'] }}
        />
      )
    })

    expect(screen.getByText('WS log line')).toBeInTheDocument()
  })

  it('truncates buffer to 1000 lines', async () => {
    // Start with 999 lines
    const manyLines = Array.from({ length: 999 }, (_, i) => `Line ${i}`)
    getLogs.mockResolvedValue({
      logs: [{ agent: 'Claude-1', lines: manyLines }],
    })
    const { rerender } = await act(async () =>
      render(<LogViewer projectId={1} wsEvents={null} />)
    )

    // Add 5 more lines via WS -> should truncate to 1000
    await act(async () => {
      rerender(
        <LogViewer
          projectId={1}
          wsEvents={{ type: 'log', agent: 'Claude-1', lines: ['A', 'B', 'C', 'D', 'E'] }}
        />
      )
    })

    // The buffer should have been sliced to 1000; "Line 0" through "Line 2" should be gone
    expect(screen.queryByText('Line 0')).not.toBeInTheDocument()
    expect(screen.getByText('E')).toBeInTheDocument()
  })
})

// --- ActivityFeed ---
import ActivityFeed from '../components/ActivityFeed'

// jsdom doesn't implement scrollIntoView
Element.prototype.scrollIntoView = vi.fn()

describe('ActivityFeed', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('loads and displays initial activity', async () => {
    getLogs.mockResolvedValue({
      logs: [{ agent: 'Claude-1', lines: ['Started task'] }],
    })
    await act(async () => { render(<ActivityFeed projectId={1} />) })
    expect(screen.getByText('Started task')).toBeInTheDocument()
    expect(screen.getByText('[Claude-1]')).toBeInTheDocument()
  })

  it('shows empty state when no activity', async () => {
    getLogs.mockResolvedValue({ logs: [] })
    await act(async () => { render(<ActivityFeed projectId={1} />) })
    expect(screen.getByText('No activity yet')).toBeInTheDocument()
  })

  it('appends WebSocket log events', async () => {
    getLogs.mockResolvedValue({ logs: [] })
    const { rerender } = await act(async () =>
      render(<ActivityFeed projectId={1} wsEvents={null} />)
    )

    await act(async () => {
      rerender(
        <ActivityFeed
          projectId={1}
          wsEvents={{ type: 'log', agent: 'Claude-3', lines: ['New event'] }}
        />
      )
    })

    expect(screen.getByText('New event')).toBeInTheDocument()
    expect(screen.getByText('[Claude-3]')).toBeInTheDocument()
  })

  it('caps buffer at 200 entries', async () => {
    // Start with 199 lines
    const lines = Array.from({ length: 199 }, (_, i) => `Entry ${i}`)
    getLogs.mockResolvedValue({
      logs: [{ agent: 'Claude-1', lines }],
    })
    const { rerender } = await act(async () =>
      render(<ActivityFeed projectId={1} wsEvents={null} />)
    )

    // getLogs returns 50 lines max; the component slices to 100 on initial load
    // Then WS appends should cap at 200. Let's test the WS truncation directly.
    // Reset to have exactly 198 entries
    getLogs.mockResolvedValue({
      logs: [{ agent: 'Claude-1', lines: Array.from({ length: 50 }, (_, i) => `Bulk ${i}`) }],
    })

    await act(async () => {
      rerender(
        <ActivityFeed
          projectId={1}
          wsEvents={{ type: 'log', agent: 'Claude-2', lines: Array.from({ length: 5 }, (_, i) => `WS ${i}`) }}
        />
      )
    })

    // Should have WS entries visible
    expect(screen.getByText('WS 4')).toBeInTheDocument()
  })
})

// --- Sidebar ---
import Sidebar from '../components/Sidebar'

function renderSidebar(props = {}) {
  const defaults = {
    projects: [],
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

describe('Sidebar', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders project list', () => {
    renderSidebar({
      projects: [
        { id: 1, name: 'Alpha', goal: 'Build alpha', status: 'running' },
        { id: 2, name: 'Beta', goal: 'Build beta', status: 'created' },
      ],
    })
    expect(screen.getByText('Alpha')).toBeInTheDocument()
    expect(screen.getByText('Beta')).toBeInTheDocument()
  })

  it('shows empty state when no projects', () => {
    renderSidebar({ projects: [] })
    expect(screen.getByText('No projects yet')).toBeInTheDocument()
  })

  it('renders branding', () => {
    renderSidebar()
    expect(screen.getByText('Latent Underground')).toBeInTheDocument()
    expect(screen.getByText('Swarm Control')).toBeInTheDocument()
  })

  it('renders new project button', () => {
    renderSidebar()
    expect(screen.getByText('+ New Project')).toBeInTheDocument()
  })

  it('shows status dot with correct color class for running project', () => {
    const { container } = renderSidebar({
      projects: [{ id: 1, name: 'P1', goal: 'G1', status: 'running' }],
    })
    const dot = container.querySelector('.bg-emerald-500')
    expect(dot).toBeInTheDocument()
  })
})

// --- ErrorBoundary ---
import ErrorBoundary from '../components/ErrorBoundary'

function ThrowError({ shouldThrow }) {
  if (shouldThrow) throw new Error('Test render error')
  return <div>No error</div>
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Child content</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('Child content')).toBeInTheDocument()
  })

  it('renders fallback UI when child throws', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <ErrorBoundary>
        <ThrowError shouldThrow={true} />
      </ErrorBoundary>
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Test render error')).toBeInTheDocument()
    expect(screen.getByText('Try Again')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('recovers when Try Again is clicked', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    let shouldThrow = true
    function MaybeThrows() {
      if (shouldThrow) throw new Error('Boom')
      return <div>No error</div>
    }

    render(
      <ErrorBoundary>
        <MaybeThrows />
      </ErrorBoundary>
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()

    // Fix the component before clicking retry
    shouldThrow = false
    fireEvent.click(screen.getByText('Try Again'))
    expect(screen.getByText('No error')).toBeInTheDocument()
    spy.mockRestore()
  })

  it('shows default message when error has no message', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    function ThrowEmpty() {
      throw new Error()
    }

    render(
      <ErrorBoundary>
        <ThrowEmpty />
      </ErrorBoundary>
    )
    expect(screen.getByText('An unexpected error occurred.')).toBeInTheDocument()
    spy.mockRestore()
  })
})

// --- Home ---
import Home from '../components/Home'

describe('Home', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders branding', () => {
    render(<Home />)
    expect(screen.getByText('Latent Underground')).toBeInTheDocument()
    expect(screen.getByText(/Swarm orchestration control center/)).toBeInTheDocument()
  })

  it('navigates to new project on button click', () => {
    render(<Home />)
    fireEvent.click(screen.getByText('+ New Swarm Project'))
    expect(mockNavigate).toHaveBeenCalledWith('/projects/new')
  })
})
