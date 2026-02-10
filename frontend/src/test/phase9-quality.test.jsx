import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'

expect.extend(matchers)

// Mock react-router-dom
const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: '1' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
  BrowserRouter: ({ children }) => <div>{children}</div>,
}))

// Mock api module
vi.mock('../lib/api', () => ({
  getProjects: vi.fn(() => Promise.resolve([])),
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test', status: 'created', config: '{}' })),
  createProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test' })),
  getTemplates: vi.fn(() => Promise.resolve([])),
  getSwarmStatus: vi.fn(() => Promise.resolve({ status: 'created', agents: [], signals: {}, tasks: { total: 0, done: 0, percent: 0 }, phase: null })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], total: 0, offset: 0, has_more: false })),
  getLogs: vi.fn(() => Promise.resolve({ lines: [] })),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 0, avg_duration_seconds: null, total_tasks_completed: 0 })),
  browseDirectory: vi.fn(() => Promise.resolve({ path: '', parent: null, dirs: [] })),
  startWatch: vi.fn(() => Promise.resolve({})),
  stopWatch: vi.fn(() => Promise.resolve({})),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched' })),
  stopSwarm: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  updateProjectConfig: vi.fn(() => Promise.resolve({})),
  createTemplate: vi.fn(() => Promise.resolve({ id: 1, name: 'New' })),
  updateTemplate: vi.fn(() => Promise.resolve({ id: 1 })),
  deleteTemplate: vi.fn(() => Promise.resolve(null)),
  searchLogs: vi.fn(() => Promise.resolve({ lines: [] })),
  getFile: vi.fn(() => Promise.resolve({ content: '# Test' })),
  putFile: vi.fn(() => Promise.resolve({})),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  updateProject: vi.fn(() => Promise.resolve({ id: 1 })),
  sendSwarmInput: vi.fn(() => Promise.resolve({})),
  getProjectAnalytics: vi.fn(() => Promise.resolve({ total_runs: 0, runs: [] })),
}))

// Mock useNotifications (used by SwarmControls) - named export
vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({ notify: vi.fn(), permission: 'granted', requestPermission: vi.fn() }),
}))

import ErrorBoundary from '../components/ErrorBoundary'
import NewProject from '../components/NewProject'
import TemplateManager from '../components/TemplateManager'
import FolderBrowser from '../components/FolderBrowser'
import Sparkline from '../components/Sparkline'
import ConfirmDialog from '../components/ConfirmDialog'
import TaskProgress from '../components/TaskProgress'
import AgentGrid from '../components/AgentGrid'
import SignalPanel from '../components/SignalPanel'
import SwarmHistory from '../components/SwarmHistory'
import SwarmControls from '../components/SwarmControls'
import Sidebar from '../components/Sidebar'
import { ToastProvider } from '../components/Toast'


// =============================================================================
// Error Boundary Tests
// =============================================================================
describe('ErrorBoundary', () => {
  // Suppress React error boundary console errors in tests
  const originalError = console.error
  beforeEach(() => {
    console.error = vi.fn()
  })
  afterEach(() => {
    console.error = originalError
  })

  function ThrowingComponent({ shouldThrow = true }) {
    if (shouldThrow) throw new Error('Test crash')
    return <div>Normal content</div>
  }

  it('renders children when no error', () => {
    render(
      <ErrorBoundary>
        <div>Hello World</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('Hello World')).toBeInTheDocument()
  })

  it('catches render errors and shows error message', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent shouldThrow={true} />
      </ErrorBoundary>
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Test crash')).toBeInTheDocument()
  })

  it('shows Try Again button on error', () => {
    render(
      <ErrorBoundary>
        <ThrowingComponent />
      </ErrorBoundary>
    )
    expect(screen.getByText('Try Again')).toBeInTheDocument()
  })

  it('recovers when Try Again is clicked', () => {
    let shouldThrow = true
    function ConditionalThrower() {
      if (shouldThrow) throw new Error('Recoverable error')
      return <div>Recovered!</div>
    }

    render(
      <ErrorBoundary>
        <ConditionalThrower />
      </ErrorBoundary>
    )

    expect(screen.getByText('Something went wrong')).toBeInTheDocument()

    // Stop throwing and click retry
    shouldThrow = false
    fireEvent.click(screen.getByText('Try Again'))

    expect(screen.getByText('Recovered!')).toBeInTheDocument()
  })

  it('shows generic message when error has no message', () => {
    function NoMessageThrower() {
      throw { notAnError: true }
    }

    render(
      <ErrorBoundary>
        <NoMessageThrower />
      </ErrorBoundary>
    )
    expect(screen.getByText('An unexpected error occurred.')).toBeInTheDocument()
  })

  it('renders multiple children correctly when no error', () => {
    render(
      <ErrorBoundary>
        <div>First child</div>
        <div>Second child</div>
      </ErrorBoundary>
    )
    expect(screen.getByText('First child')).toBeInTheDocument()
    expect(screen.getByText('Second child')).toBeInTheDocument()
  })

  it('shows the exact error message from thrown Error', () => {
    function SpecificErrorThrower() {
      throw new Error('Database connection timeout after 5000ms')
    }

    render(
      <ErrorBoundary>
        <SpecificErrorThrower />
      </ErrorBoundary>
    )
    expect(screen.getByText('Database connection timeout after 5000ms')).toBeInTheDocument()
  })

  it('catches errors from deeply nested children', () => {
    function DeepChild() {
      throw new Error('Deep error')
    }
    function MiddleComponent() {
      return <div><DeepChild /></div>
    }

    render(
      <ErrorBoundary>
        <div>
          <MiddleComponent />
        </div>
      </ErrorBoundary>
    )
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
    expect(screen.getByText('Deep error')).toBeInTheDocument()
  })

  it('isolates errors - sibling content outside boundary is unaffected', () => {
    function Thrower() {
      throw new Error('Isolated error')
    }

    render(
      <div>
        <div>Outside boundary</div>
        <ErrorBoundary>
          <Thrower />
        </ErrorBoundary>
      </div>
    )
    expect(screen.getByText('Outside boundary')).toBeInTheDocument()
    expect(screen.getByText('Something went wrong')).toBeInTheDocument()
  })

  it('can recover after retry and render normally', () => {
    // Use a mutable ref that we control externally to avoid
    // React concurrent rendering re-invoking the component body
    let shouldThrow = true
    function ControlledThrower() {
      if (shouldThrow) throw new Error('Will recover')
      return <div>Recovered content</div>
    }

    render(
      <ErrorBoundary>
        <ControlledThrower />
      </ErrorBoundary>
    )

    // Error is caught
    expect(screen.getByText('Will recover')).toBeInTheDocument()
    expect(screen.getByText('Try Again')).toBeInTheDocument()

    // Allow recovery
    shouldThrow = false
    fireEvent.click(screen.getByText('Try Again'))

    // Now renders normally
    expect(screen.getByText('Recovered content')).toBeInTheDocument()
    expect(screen.queryByText('Something went wrong')).not.toBeInTheDocument()
  })
})


// =============================================================================
// Accessibility Tests using vitest-axe (axe-core)
// =============================================================================
describe('Accessibility audit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('NewProject has no accessibility violations', async () => {
    const { getTemplates } = await import('../lib/api')
    getTemplates.mockResolvedValue([])

    let container
    await act(async () => {
      const result = render(
        <ToastProvider>
          <NewProject onProjectChange={vi.fn()} />
        </ToastProvider>
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('TemplateManager has no accessibility violations', async () => {
    const { getTemplates } = await import('../lib/api')
    getTemplates.mockResolvedValue([
      { id: 1, name: 'Template A', description: 'Desc', config: { agent_count: 4, max_phases: 6 } },
    ])

    let container
    await act(async () => {
      const result = render(
        <ToastProvider>
          <TemplateManager onTemplatesChange={vi.fn()} />
        </ToastProvider>
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('FolderBrowser dialog has no accessibility violations', async () => {
    const { browseDirectory } = await import('../lib/api')
    browseDirectory.mockResolvedValue({
      path: 'C:\\Projects',
      parent: 'C:\\',
      dirs: [{ name: 'my-app', path: 'C:\\Projects\\my-app' }],
    })

    let container
    await act(async () => {
      const result = render(
        <FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('ConfirmDialog has no accessibility violations', async () => {
    const { container } = render(
      <ConfirmDialog
        open={true}
        title="Confirm Action"
        message="Are you sure?"
        confirmLabel="Yes"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('Sparkline has no accessibility violations', async () => {
    const { container } = render(
      <Sparkline data={[1, 2, 3, 4, 5]} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('Sparkline with no data has no accessibility violations', async () => {
    const { container } = render(
      <Sparkline data={[]} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('Sparkline with single data point has no accessibility violations', async () => {
    const { container } = render(
      <Sparkline data={[42]} />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('ErrorBoundary error state has no accessibility violations', async () => {
    // Suppress React error boundary console errors
    const originalError = console.error
    console.error = vi.fn()

    function Thrower() {
      throw new Error('A11y test error')
    }

    const { container } = render(
      <ErrorBoundary>
        <Thrower />
      </ErrorBoundary>
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()

    console.error = originalError
  })

  it('ConfirmDialog with danger variant has no accessibility violations', async () => {
    const { container } = render(
      <ConfirmDialog
        open={true}
        title="Delete Item"
        message="This action cannot be undone."
        confirmLabel="Delete"
        cancelLabel="Keep"
        danger={true}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('FolderBrowser with empty directory list has no violations', async () => {
    const { browseDirectory } = await import('../lib/api')
    browseDirectory.mockResolvedValue({
      path: 'C:\\Empty',
      parent: 'C:\\',
      dirs: [],
    })

    let container
    await act(async () => {
      const result = render(
        <FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})


// =============================================================================
// Performance Benchmark Tests
// =============================================================================
describe('Performance benchmarks', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('Sparkline renders 1000 data points within 100ms', () => {
    const data = Array.from({ length: 1000 }, (_, i) => Math.sin(i / 10) * 50 + 50)
    const start = performance.now()

    const { container } = render(<Sparkline data={data} />)

    const elapsed = performance.now() - start
    expect(elapsed).toBeLessThan(100)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })

  it('Sparkline renders 5000 data points within 200ms', () => {
    const data = Array.from({ length: 5000 }, (_, i) => Math.random() * 100)
    const start = performance.now()

    const { container } = render(<Sparkline data={data} />)

    const elapsed = performance.now() - start
    expect(elapsed).toBeLessThan(200)
    expect(container.querySelector('svg polyline')).toBeInTheDocument()
  })

  it('renders 50 templates in list without excessive lag', async () => {
    const { getTemplates } = await import('../lib/api')
    const templates = Array.from({ length: 50 }, (_, i) => ({
      id: i + 1,
      name: `Template ${i + 1}`,
      description: `Description ${i + 1}`,
      config: { agent_count: 4, max_phases: 6 },
    }))
    getTemplates.mockResolvedValue(templates)

    const start = performance.now()
    await act(async () => {
      render(
        <ToastProvider>
          <TemplateManager onTemplatesChange={vi.fn()} />
        </ToastProvider>
      )
    })
    const elapsed = performance.now() - start

    expect(elapsed).toBeLessThan(500)
    expect(screen.getByText('Template 1')).toBeInTheDocument()
    expect(screen.getByText('Template 50')).toBeInTheDocument()
  })

  it('FolderBrowser handles 500 directories efficiently', async () => {
    const { browseDirectory } = await import('../lib/api')
    const dirs = Array.from({ length: 500 }, (_, i) => ({
      name: `dir-${String(i).padStart(3, '0')}`,
      path: `C:\\dirs\\dir-${String(i).padStart(3, '0')}`,
    }))
    browseDirectory.mockResolvedValue({ path: 'C:\\dirs', parent: 'C:\\', dirs })

    const start = performance.now()
    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })
    const elapsed = performance.now() - start

    expect(elapsed).toBeLessThan(1000)
    expect(screen.getByText('dir-000')).toBeInTheDocument()
    expect(screen.getByText('dir-499')).toBeInTheDocument()
  })

  it('ErrorBoundary renders children with minimal overhead', () => {
    const iterations = 100
    const children = Array.from({ length: iterations }, (_, i) => (
      <div key={i}>Child {i}</div>
    ))

    const start = performance.now()
    render(<ErrorBoundary>{children}</ErrorBoundary>)
    const elapsed = performance.now() - start

    expect(elapsed).toBeLessThan(200)
    expect(screen.getByText('Child 0')).toBeInTheDocument()
    expect(screen.getByText('Child 99')).toBeInTheDocument()
  })

  it('ConfirmDialog mount/unmount cycle is fast', () => {
    const start = performance.now()

    for (let i = 0; i < 20; i++) {
      const { unmount } = render(
        <ConfirmDialog
          open={true}
          title={`Confirm ${i}`}
          message={`Message ${i}`}
          onConfirm={vi.fn()}
          onCancel={vi.fn()}
        />
      )
      unmount()
    }

    const elapsed = performance.now() - start
    expect(elapsed).toBeLessThan(500)
  })

  it('Sparkline handles rapid re-renders efficiently', () => {
    const { rerender, container } = render(<Sparkline data={[1, 2, 3]} />)

    const start = performance.now()
    for (let i = 0; i < 50; i++) {
      const data = Array.from({ length: 20 }, () => Math.random() * 100)
      rerender(<Sparkline data={data} />)
    }
    const elapsed = performance.now() - start

    expect(elapsed).toBeLessThan(200)
    expect(container.querySelector('svg')).toBeInTheDocument()
  })
})


// =============================================================================
// Extended Accessibility Audit - Remaining Components
// =============================================================================
describe('Extended accessibility audit', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('TaskProgress has no accessibility violations', async () => {
    const { container } = render(
      <TaskProgress tasks={{ total: 10, done: 7, percent: 70 }} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('TaskProgress at 0% has no accessibility violations', async () => {
    const { container } = render(
      <TaskProgress tasks={{ total: 0, done: 0, percent: 0 }} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('TaskProgress at 100% has no accessibility violations', async () => {
    const { container } = render(
      <TaskProgress tasks={{ total: 10, done: 10, percent: 100 }} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('AgentGrid has no accessibility violations', async () => {
    const agents = [
      { name: 'Claude-1', last_heartbeat: new Date().toISOString() },
      { name: 'Claude-2', last_heartbeat: new Date(Date.now() - 300000).toISOString() },
      { name: 'Claude-3', last_heartbeat: null },
    ]
    const { container } = render(<AgentGrid agents={agents} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('AgentGrid with empty agents has no accessibility violations', async () => {
    const { container } = render(<AgentGrid agents={[]} />)
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SignalPanel has no accessibility violations', async () => {
    const signals = {
      'backend-ready': true,
      'frontend-ready': true,
      'tests-passing': false,
      'phase-complete': false,
    }
    const phase = { Phase: 3, MaxPhases: 24 }
    const { container } = render(
      <SignalPanel signals={signals} phase={phase} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SignalPanel with all signals active has no violations', async () => {
    const signals = {
      'backend-ready': true,
      'frontend-ready': true,
      'tests-passing': true,
      'phase-complete': true,
    }
    const phase = { Phase: 24, MaxPhases: 24 }
    const { container } = render(
      <SignalPanel signals={signals} phase={phase} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SwarmHistory has no accessibility violations', async () => {
    const mockHistory = vi.fn(() => Promise.resolve({
      runs: [
        { id: 1, started_at: '2024-01-01T12:00:00', duration_seconds: 120, status: 'stopped', tasks_completed: 5 },
        { id: 2, started_at: '2024-01-02T14:00:00', duration_seconds: 300, status: 'completed', tasks_completed: 12 },
      ],
    }))

    let container
    await act(async () => {
      const result = render(
        <SwarmHistory projectId={1} fetchHistory={mockHistory} />
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SwarmHistory with empty runs has no violations', async () => {
    const mockHistory = vi.fn(() => Promise.resolve({ runs: [] }))

    let container
    await act(async () => {
      const result = render(
        <SwarmHistory projectId={1} fetchHistory={mockHistory} />
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SwarmControls (created status) has no accessibility violations', async () => {
    let container
    await act(async () => {
      const result = render(
        <ToastProvider>
          <SwarmControls projectId={1} status="created" onAction={vi.fn()} />
        </ToastProvider>
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('SwarmControls (running status) has no accessibility violations', async () => {
    let container
    await act(async () => {
      const result = render(
        <ToastProvider>
          <SwarmControls projectId={1} status="running" onAction={vi.fn()} />
        </ToastProvider>
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('Sidebar with projects has no accessibility violations', async () => {
    const projects = [
      { id: 1, name: 'Alpha Project', goal: 'Build API', status: 'running' },
      { id: 2, name: 'Beta Project', goal: 'Build UI', status: 'created' },
      { id: 3, name: 'Gamma Project', goal: 'Testing', status: 'completed' },
    ]

    let container
    await act(async () => {
      const result = render(
        <ToastProvider>
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} />
        </ToastProvider>
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('Sidebar empty state has no accessibility violations', async () => {
    let container
    await act(async () => {
      const result = render(
        <ToastProvider>
          <Sidebar projects={[]} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} />
        </ToastProvider>
      )
      container = result.container
    })

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
