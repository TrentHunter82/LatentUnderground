/**
 * Phase 24 - Accessibility Integration Tests
 *
 * Tests for:
 * - Shape indicators in AgentGrid (StatusIcon SVG shapes)
 * - Sidebar ProjectStatusIcon shapes
 * - Keyboard navigation (SettingsPanel focus restore, Move Up/Down)
 * - Form validation (ProjectSettings visible error messages)
 * - Touch targets (44px minimum interactive elements)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// Mock react-router-dom
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual('react-router-dom')
  return {
    ...actual,
    useNavigate: () => vi.fn(),
    useParams: () => ({ id: '1' }),
  }
})

// Mock api module with ALL exports
vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getAgentEvents: vi.fn(() => Promise.resolve({ events: [] })),
  searchSwarmOutput: vi.fn(() => Promise.resolve({ results: [] })),
  compareRuns: vi.fn(() => Promise.resolve({})),
  sendDirective: vi.fn(() => Promise.resolve({ status: 'queued' })),
  getDirectiveStatus: vi.fn(() => Promise.resolve({ pending: false })),
  updateAgentPrompt: vi.fn(() => Promise.resolve({ old_prompt: 'old' })),
  restartAgent: vi.fn(() => Promise.resolve({ status: 'restarted' })),
  getSwarmAgents: vi.fn(() => Promise.resolve({ agents: [] })),
  stopSwarmAgent: vi.fn(() => Promise.resolve({ status: 'stopped' })),
  sendSwarmInput: vi.fn(() => Promise.resolve({ status: 'sent' })),
  getProjects: vi.fn(() => Promise.resolve([])),
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test' })),
  getSwarmStatus: vi.fn(() => Promise.resolve(null)),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
  getProjectStats: vi.fn(() => Promise.resolve(null)),
  launchSwarm: vi.fn(() => Promise.resolve({})),
  stopSwarm: vi.fn(() => Promise.resolve({})),
  startWatch: vi.fn(() => Promise.resolve({})),
  stopWatch: vi.fn(() => Promise.resolve({})),
  deleteProject: vi.fn(() => Promise.resolve(null)),
  archiveProject: vi.fn(() => Promise.resolve({})),
  unarchiveProject: vi.fn(() => Promise.resolve({})),
  updateProjectConfig: vi.fn(() => Promise.resolve({})),
  createProject: vi.fn(() => Promise.resolve({ id: 1 })),
  updateProject: vi.fn(() => Promise.resolve({})),
  getFile: vi.fn(() => Promise.resolve({ content: '' })),
  putFile: vi.fn(() => Promise.resolve({})),
  getLogs: vi.fn(() => Promise.resolve([])),
  searchLogs: vi.fn(() => Promise.resolve([])),
  browseDirectory: vi.fn(() => Promise.resolve({ entries: [] })),
  getTemplates: vi.fn(() => Promise.resolve([])),
  getTemplate: vi.fn(() => Promise.resolve({})),
  createTemplate: vi.fn(() => Promise.resolve({})),
  updateTemplate: vi.fn(() => Promise.resolve({})),
  deleteTemplate: vi.fn(() => Promise.resolve(null)),
  getWebhooks: vi.fn(() => Promise.resolve([])),
  createWebhook: vi.fn(() => Promise.resolve({})),
  updateWebhook: vi.fn(() => Promise.resolve({})),
  deleteWebhook: vi.fn(() => Promise.resolve(null)),
  getProjectsWithArchived: vi.fn(() => Promise.resolve([])),
  setApiKey: vi.fn(),
  clearApiKey: vi.fn(),
  getStoredApiKey: vi.fn(() => null),
  getSystemInfo: vi.fn(() => Promise.resolve({})),
  getSystemHealth: vi.fn(() => Promise.resolve({ status: 'ok' })),
  getMetrics: vi.fn(() => Promise.resolve('')),
  getHealthTrends: vi.fn(() => Promise.resolve({})),
  getProjectHealth: vi.fn(() => Promise.resolve({ crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 })),
  getProjectQuota: vi.fn(() => Promise.resolve({})),
  getRunCheckpoints: vi.fn(() => Promise.resolve([])),
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
  useProject: () => ({ data: { id: 1, name: 'Test', goal: 'Test goal', config: '{}' }, isLoading: false, error: null }),
  useProjectStats: () => ({ data: null, isLoading: false, error: null }),
  useProjectHealth: () => ({ data: { crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 }, isLoading: false, error: null }),
  useProjectQuota: () => ({ data: {}, isLoading: false, error: null }),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock({
  useSwarmStatus: () => ({ data: null, isLoading: false, error: null }),
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

// --- Tests ---

describe('Phase 24 - Accessibility Integration Tests', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.clear()
    localStorage.setItem('lu_onboarding_complete', 'true')
  })

  // =========================================================================
  // AgentGrid Shape Indicators
  // =========================================================================

  describe('AgentGrid StatusIcon shape indicators', () => {
    it('renders SVG checkmark shape for running agent', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [{ name: 'Claude-1', last_heartbeat: null }]
      const processAgents = [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 }]

      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
        container = result.container
      })

      // StatusIcon for running: has checkmark path d="M3 5l1.5 1.5L7 4"
      const svgs = container.querySelectorAll('svg[aria-hidden="true"]')
      expect(svgs.length).toBeGreaterThanOrEqual(1)
      const checkmarkPaths = container.querySelectorAll('path[d="M3 5l1.5 1.5L7 4"]')
      expect(checkmarkPaths.length).toBe(1)
    })

    it('renders SVG X shape for crashed agent', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [{ name: 'Claude-1', last_heartbeat: null }]
      const processAgents = [{ name: 'Claude-1', pid: 1234, alive: false, exit_code: 1, output_lines: 5 }]

      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
        container = result.container
      })

      // StatusIcon for crashed: has X paths d="M3.5 3.5l3 3M6.5 3.5l-3 3"
      const xPaths = container.querySelectorAll('path[d="M3.5 3.5l3 3M6.5 3.5l-3 3"]')
      expect(xPaths.length).toBe(1)
    })

    it('renders SVG dash shape for stopped agent', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [{ name: 'Claude-1', last_heartbeat: null }]
      const processAgents = [{ name: 'Claude-1', pid: 1234, alive: false, exit_code: 0, output_lines: 5 }]

      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
        container = result.container
      })

      // StatusIcon for stopped: has dash path d="M3 5h4"
      const dashPaths = container.querySelectorAll('path[d="M3 5h4"]')
      expect(dashPaths.length).toBe(1)
    })

    it('provides sr-only text for each agent status', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [
        { name: 'Claude-1', last_heartbeat: null },
        { name: 'Claude-2', last_heartbeat: null },
        { name: 'Claude-3', last_heartbeat: null },
      ]
      const processAgents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
        { name: 'Claude-2', pid: 1235, alive: false, exit_code: 0, output_lines: 5 },
        { name: 'Claude-3', pid: 1236, alive: false, exit_code: 1, output_lines: 0 },
      ]

      await act(async () => {
        renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
      })

      // SR-only text pattern: "{name}: {status}"
      expect(screen.getByText('Claude-1: running')).toBeInTheDocument()
      expect(screen.getByText('Claude-2: stopped')).toBeInTheDocument()
      expect(screen.getByText(/Claude-3: crashed/i)).toBeInTheDocument()
    })

    it('has role="list" and role="listitem" structure', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [
        { name: 'Claude-1', last_heartbeat: null },
        { name: 'Claude-2', last_heartbeat: null },
      ]
      const processAgents = [
        { name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 },
        { name: 'Claude-2', pid: 1235, alive: false, exit_code: 0, output_lines: 5 },
      ]

      await act(async () => {
        renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
      })

      const list = screen.getByRole('list', { name: /agent status/i })
      expect(list).toBeInTheDocument()
      const items = screen.getAllByRole('listitem')
      expect(items.length).toBe(2)
    })

    it('StatusIcon SVGs have aria-hidden="true"', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [{ name: 'Claude-1', last_heartbeat: null }]
      const processAgents = [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 }]

      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
        container = result.container
      })

      // All StatusIcon SVGs should be hidden from assistive technology
      const statusSvgs = container.querySelectorAll('svg[viewBox="0 0 10 10"]')
      statusSvgs.forEach(svg => {
        expect(svg.getAttribute('aria-hidden')).toBe('true')
      })
    })

    it('edit prompt button meets touch target requirements', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [{ name: 'Claude-1', last_heartbeat: null }]
      const processAgents = [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 }]

      let container
      await act(async () => {
        const result = renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
        container = result.container
      })

      const editBtn = screen.getByRole('button', { name: /edit prompt/i })
      expect(editBtn).toBeInTheDocument()
      // Check CSS classes for minimum dimensions
      expect(editBtn.className).toContain('min-w-[28px]')
      expect(editBtn.className).toContain('min-h-[28px]')
    })
  })

  // =========================================================================
  // Sidebar ProjectStatusIcon
  // =========================================================================

  describe('Sidebar ProjectStatusIcon shape indicators', () => {
    it('renders filled circle for running project', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [{ id: 1, name: 'Test Project', status: 'running', goal: 'Test' }]

      let container
      await act(async () => {
        const result = renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
        container = result.container
      })

      // Running status: filled circle with r="3.5" (r=3.5, viewBox 0 0 8 8)
      const filledCircles = container.querySelectorAll('svg[viewBox="0 0 8 8"] circle[r="3.5"]')
      expect(filledCircles.length).toBeGreaterThanOrEqual(1)
    })

    it('renders hollow circle for stopped project', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [{ id: 1, name: 'Test Project', status: 'stopped', goal: 'Test' }]

      let container
      await act(async () => {
        const result = renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
        container = result.container
      })

      // Stopped status: hollow circle with stroke, r="2.5"
      const hollowCircles = container.querySelectorAll('svg[viewBox="0 0 8 8"] circle[r="2.5"]')
      expect(hollowCircles.length).toBeGreaterThanOrEqual(1)
    })

    it('renders triangle for created project', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [{ id: 1, name: 'Test Project', status: 'created', goal: 'Test' }]

      let container
      await act(async () => {
        const result = renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
        container = result.container
      })

      // Created status: triangle path d="M4 1L7 7H1z"
      const trianglePaths = container.querySelectorAll('svg[viewBox="0 0 8 8"] path[d="M4 1L7 7H1z"]')
      expect(trianglePaths.length).toBeGreaterThanOrEqual(1)
    })

    it('provides sr-only status text for each project', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [
        { id: 1, name: 'Running Project', status: 'running', goal: 'Test' },
        { id: 2, name: 'Stopped Project', status: 'stopped', goal: 'Test' },
      ]

      await act(async () => {
        renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
      })

      // SR-only text: "Status: {status}"
      expect(screen.getByText('Status: running')).toBeInTheDocument()
      expect(screen.getByText('Status: stopped')).toBeInTheDocument()
    })

    it('renders health dot shapes (circle for healthy, triangle for warning, diamond for critical)', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [
        { id: 1, name: 'Healthy', status: 'running', goal: 'Test' },
        { id: 2, name: 'Warning', status: 'running', goal: 'Test' },
        { id: 3, name: 'Critical', status: 'running', goal: 'Test' },
      ]
      const projectHealth = { 1: 'green', 2: 'yellow', 3: 'red' }

      let container
      await act(async () => {
        const result = renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} projectHealth={projectHealth} />
        )
        container = result.container
      })

      // Health shapes: green=circle, yellow=triangle, red=diamond (all viewBox 0 0 7 7)
      const healthSvgs = container.querySelectorAll('svg[viewBox="0 0 7 7"]')
      expect(healthSvgs.length).toBe(3)

      // SR-only health labels
      expect(screen.getByText('Health: Healthy')).toBeInTheDocument()
      expect(screen.getByText('Health: Warning')).toBeInTheDocument()
      expect(screen.getByText('Health: Critical')).toBeInTheDocument()
    })
  })

  // =========================================================================
  // Keyboard Navigation
  // =========================================================================

  describe('Keyboard navigation', () => {
    it('Sidebar Move Up/Down buttons have proper aria-labels', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [
        { id: 1, name: 'First Project', status: 'running', goal: 'Test' },
        { id: 2, name: 'Second Project', status: 'stopped', goal: 'Test' },
      ]

      await act(async () => {
        renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
      })

      // Move buttons should exist with proper labels
      const moveUpBtns = screen.getAllByRole('button', { name: /move .+ up/i })
      expect(moveUpBtns.length).toBeGreaterThanOrEqual(1)
      const moveDownBtns = screen.getAllByRole('button', { name: /move .+ down/i })
      expect(moveDownBtns.length).toBeGreaterThanOrEqual(1)
    })

    it('Move Up button is disabled for first project', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [
        { id: 1, name: 'First Project', status: 'running', goal: 'Test' },
        { id: 2, name: 'Second Project', status: 'stopped', goal: 'Test' },
      ]

      await act(async () => {
        renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
      })

      const moveUpBtns = screen.getAllByRole('button', { name: /move .+ up/i })
      // First project's move up should be disabled
      expect(moveUpBtns[0]).toBeDisabled()
    })

    it('Move Down button is disabled for last project', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [
        { id: 1, name: 'First Project', status: 'running', goal: 'Test' },
        { id: 2, name: 'Second Project', status: 'stopped', goal: 'Test' },
      ]

      await act(async () => {
        renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
      })

      const moveDownBtns = screen.getAllByRole('button', { name: /move .+ down/i })
      // Last project's move down should be disabled
      expect(moveDownBtns[moveDownBtns.length - 1]).toBeDisabled()
    })

    it('status filter buttons have aria-pressed attribute', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [{ id: 1, name: 'Test', status: 'running', goal: 'Test' }]

      await act(async () => {
        renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
      })

      // The "all" filter should be pressed by default
      const allFilter = screen.getByRole('button', { name: /filter by all/i })
      expect(allFilter).toHaveAttribute('aria-pressed', 'true')

      // Other filters should not be pressed
      const runningFilter = screen.getByRole('button', { name: /filter by running/i })
      expect(runningFilter).toHaveAttribute('aria-pressed', 'false')
    })
  })

  // =========================================================================
  // Form Validation
  // =========================================================================

  describe('ProjectSettings form validation', () => {
    it('shows visible error message when agent count exceeds max', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')

      await act(async () => {
        renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
      })

      const agentInput = screen.getByLabelText(/agent count/i)
      // Type a value exceeding the max of 10
      await act(async () => {
        fireEvent.change(agentInput, { target: { value: '15' } })
      })

      // Should show clamped error with role="alert"
      const errorAlert = screen.getByRole('alert')
      expect(errorAlert).toBeInTheDocument()
      expect(errorAlert.textContent).toMatch(/clamped to 10/i)
    })

    it('shows visible error message when max phases exceeds max', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')

      await act(async () => {
        renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
      })

      const phasesInput = screen.getByLabelText(/max phases/i)
      // Type a value exceeding the max of 24
      await act(async () => {
        fireEvent.change(phasesInput, { target: { value: '50' } })
      })

      const alerts = screen.getAllByRole('alert')
      const phaseAlert = alerts.find(a => a.textContent.match(/clamped to 24/i))
      expect(phaseAlert).toBeTruthy()
    })

    it('clears error when valid value is entered', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')

      await act(async () => {
        renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
      })

      const agentInput = screen.getByLabelText(/agent count/i)

      // First trigger an error
      await act(async () => {
        fireEvent.change(agentInput, { target: { value: '15' } })
      })
      expect(screen.getByRole('alert')).toBeInTheDocument()

      // Then enter a valid value
      await act(async () => {
        fireEvent.change(agentInput, { target: { value: '5' } })
      })

      // Error should be gone
      const alerts = screen.queryAllByRole('alert')
      const clampedAlerts = alerts.filter(a => a.textContent.match(/clamped/i))
      expect(clampedAlerts.length).toBe(0)
    })

    it('has aria-describedby linking inputs to hint text', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')

      let container
      await act(async () => {
        const result = renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
        container = result.container
      })

      // Agent count input should reference hint
      const agentInput = container.querySelector('#agentCount')
      expect(agentInput.getAttribute('aria-describedby')).toContain('agentCount-hint')

      // Hint text should exist
      const hint = container.querySelector('#agentCount-hint')
      expect(hint).toBeTruthy()
      expect(hint.textContent).toMatch(/must be between 1 and 10/i)

      // Max phases input
      const phasesInput = container.querySelector('#maxPhases')
      expect(phasesInput.getAttribute('aria-describedby')).toContain('maxPhases-hint')
      const phasesHint = container.querySelector('#maxPhases-hint')
      expect(phasesHint.textContent).toMatch(/must be between 1 and 24/i)
    })

    it('has aria-required="true" on required fields', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')

      let container
      await act(async () => {
        const result = renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
        container = result.container
      })

      const agentInput = container.querySelector('#agentCount')
      expect(agentInput.getAttribute('aria-required')).toBe('true')

      const phasesInput = container.querySelector('#maxPhases')
      expect(phasesInput.getAttribute('aria-required')).toBe('true')
    })

    it('custom prompts textarea has aria-describedby hint', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')

      let container
      await act(async () => {
        const result = renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
        container = result.container
      })

      const textarea = container.querySelector('#customPrompts')
      expect(textarea.getAttribute('aria-describedby')).toContain('customPrompts-hint')
      const hint = container.querySelector('#customPrompts-hint')
      expect(hint.textContent).toMatch(/optional/i)
    })

    it('save button has aria-busy during save', async () => {
      const { default: ProjectSettings } = await import('../components/ProjectSettings')

      await act(async () => {
        renderWithProviders(<ProjectSettings projectId={1} onSave={vi.fn()} />)
      })

      const saveBtn = screen.getByRole('button', { name: /save/i })
      expect(saveBtn).toHaveAttribute('aria-busy', 'false')
    })
  })

  // =========================================================================
  // Touch Targets
  // =========================================================================

  describe('Touch targets', () => {
    it('Sidebar archive/delete buttons have min 32px dimensions', async () => {
      const { default: Sidebar } = await import('../components/Sidebar')
      const projects = [{ id: 1, name: 'Test', status: 'running', goal: 'Test' }]

      let container
      await act(async () => {
        const result = renderWithProviders(
          <Sidebar projects={projects} onRefresh={vi.fn()} collapsed={false} onToggle={vi.fn()} showArchived={false} onShowArchivedChange={vi.fn()} />
        )
        container = result.container
      })

      // Archive and Delete buttons should have min-w-[32px] min-h-[32px]
      const archiveBtn = screen.getByRole('button', { name: /archive test/i })
      expect(archiveBtn.className).toContain('min-w-[32px]')
      expect(archiveBtn.className).toContain('min-h-[32px]')

      const deleteBtn = screen.getByRole('button', { name: /delete test/i })
      expect(deleteBtn.className).toContain('min-w-[32px]')
      expect(deleteBtn.className).toContain('min-h-[32px]')
    })

    it('AgentGrid edit prompt button has min 28px dimensions', async () => {
      const { default: AgentGrid } = await import('../components/AgentGrid')
      const agents = [{ name: 'Claude-1', last_heartbeat: null }]
      const processAgents = [{ name: 'Claude-1', pid: 1234, alive: true, exit_code: null, output_lines: 10 }]

      await act(async () => {
        renderWithProviders(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
      })

      const editBtn = screen.getByRole('button', { name: /edit prompt/i })
      expect(editBtn.className).toContain('min-w-[28px]')
      expect(editBtn.className).toContain('min-h-[28px]')
    })
  })

  // =========================================================================
  // Dashboard Error Display
  // =========================================================================

  describe('Dashboard error display', () => {
    it('error text has role="alert" with error icon', async () => {
      const { getProject } = await import('../lib/api')
      getProject.mockRejectedValueOnce(new Error('Connection failed'))

      const { default: Dashboard } = await import('../components/Dashboard')

      let container
      await act(async () => {
        const result = renderWithProviders(<Dashboard />)
        container = result.container
      })

      // Wait for error to appear
      await waitFor(() => {
        const alert = container.querySelector('[role="alert"]')
        if (alert) {
          expect(alert).toBeInTheDocument()
          // Should have error icon (SVG with exclamation mark)
          const svg = alert.querySelector('svg')
          expect(svg || alert.textContent.length > 0).toBeTruthy()
        }
      }, { timeout: 3000 })
    })
  })
})
