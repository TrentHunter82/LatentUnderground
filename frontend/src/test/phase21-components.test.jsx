import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: '1' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}))

const { createApiMock, createSwarmQueryMock, createMutationsMock } = await vi.hoisted(() => import('./test-utils'))

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
  getProjectQuota: vi.fn(() => Promise.resolve({ project_id: 1, quota: {}, usage: {} })),
  getProjectHealth: vi.fn(() => Promise.resolve({ project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable', run_count: 0 })),
  getHealthTrends: vi.fn(() => Promise.resolve({ projects: [], computed_at: new Date().toISOString() })),
  getRunCheckpoints: vi.fn(() => Promise.resolve({ run_id: 1, checkpoints: [], total: 0 })),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock())
vi.mock('../hooks/useMutations', () => createMutationsMock())

import { getAgentEvents, sendDirective, getDirectiveStatus, updateAgentPrompt, restartAgent, getSwarmHistory, compareRuns, stopSwarm, launchSwarm, sendSwarmInput, getSwarmAgents } from '../lib/api'
import { ToastProvider } from '../components/Toast'
import AgentEventLog from '../components/AgentEventLog'
import RunSummary from '../components/RunSummary'
import RunComparison from '../components/RunComparison'
import DirectivePanel from '../components/DirectivePanel'
import PromptEditorModal from '../components/PromptEditorModal'
import SwarmHistory from '../components/SwarmHistory'
import SwarmControls from '../components/SwarmControls'
import AgentGrid from '../components/AgentGrid'

function wrap(ui) {
  return render(<ToastProvider>{ui}</ToastProvider>)
}

// --- AgentEventLog ---
describe('AgentEventLog', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders loading skeleton initially', () => {
    getAgentEvents.mockReturnValue(new Promise(() => {})) // never resolves
    wrap(<AgentEventLog projectId={1} />)
    expect(screen.getByText('Agent Events')).toBeTruthy()
  })

  it('renders events when loaded', async () => {
    getAgentEvents.mockResolvedValue({
      events: [
        { id: 1, agent_name: 'Claude-1', event_type: 'agent_started', detail: 'Agent started', timestamp: '2024-01-01T12:00:00Z' },
        { id: 2, agent_name: 'Claude-2', event_type: 'agent_crashed', detail: 'Exit code 1', timestamp: '2024-01-01T12:05:00Z' },
      ]
    })
    wrap(<AgentEventLog projectId={1} />)
    await waitFor(() => expect(screen.getByText('2 events')).toBeTruthy())
    expect(screen.getByText('Agent started')).toBeTruthy()
    expect(screen.getByText('Exit code 1')).toBeTruthy()
  })

  it('shows empty state when no events', async () => {
    getAgentEvents.mockResolvedValue({ events: [] })
    wrap(<AgentEventLog projectId={1} />)
    await waitFor(() => expect(screen.getByText('No events recorded')).toBeTruthy())
  })

  it('filters by agent', async () => {
    getAgentEvents.mockResolvedValue({ events: [] })
    wrap(<AgentEventLog projectId={1} />)
    await waitFor(() => expect(screen.getByLabelText('Filter by agent')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Filter by agent'), { target: { value: 'Claude-1' } })
    await waitFor(() => {
      expect(getAgentEvents).toHaveBeenCalledWith(1, expect.objectContaining({ agent: 'Claude-1' }))
    })
  })

  it('handles API error gracefully', async () => {
    getAgentEvents.mockRejectedValue(new Error('Not found'))
    wrap(<AgentEventLog projectId={1} />)
    await waitFor(() => expect(screen.getByText('Events not available yet')).toBeTruthy())
  })
})

// --- RunSummary ---
describe('RunSummary', () => {
  it('renders null when no run provided', () => {
    const { container } = wrap(<RunSummary run={null} agents={null} />)
    expect(container.textContent).toBe('')
  })

  it('renders summary with success verdict', () => {
    const run = { id: 1, duration_seconds: 300, tasks_completed: 10, status: 'stopped' }
    const agents = [
      { name: 'Claude-1', alive: false, exit_code: 0 },
      { name: 'Claude-2', alive: false, exit_code: 0 },
    ]
    wrap(<RunSummary run={run} agents={agents} />)
    expect(screen.getByText('Run Summary')).toBeTruthy()
    expect(screen.getByText('Success')).toBeTruthy()
    expect(screen.getByText('5m 0s')).toBeTruthy()
    expect(screen.getByText('2')).toBeTruthy() // agent count
  })

  it('shows crashed count when agents have nonzero exit', () => {
    const run = { id: 1, duration_seconds: 120, status: 'stopped' }
    const agents = [
      { name: 'Claude-1', alive: false, exit_code: 0 },
      { name: 'Claude-2', alive: false, exit_code: 1 },
    ]
    wrap(<RunSummary run={run} agents={agents} />)
    expect(screen.getByText('1 crashed')).toBeTruthy()
  })

  it('renders per-agent table', () => {
    const run = { id: 1, duration_seconds: 60 }
    const agents = [
      { name: 'Claude-1', alive: false, exit_code: 0, output_lines: 100 },
    ]
    wrap(<RunSummary run={run} agents={agents} />)
    expect(screen.getByText('Claude-1')).toBeTruthy()
    expect(screen.getByText('Stopped')).toBeTruthy()
    expect(screen.getByText('100')).toBeTruthy()
  })
})

// --- RunComparison ---
describe('RunComparison', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders null when no runs provided', () => {
    const { container } = wrap(<RunComparison runA={null} runB={null} />)
    expect(container.textContent).toBe('')
  })

  it('renders comparison using local fallback', async () => {
    compareRuns.mockRejectedValue(new Error('not implemented'))
    const runA = { id: 1, duration_seconds: 100, tasks_completed: 5, status: 'stopped' }
    const runB = { id: 2, duration_seconds: 200, tasks_completed: 10, status: 'stopped' }
    wrap(<RunComparison runA={runA} runB={runB} />)
    await waitFor(() => expect(screen.getByText('Run Comparison')).toBeTruthy())
    // Should show "Improved" since runB has more tasks
    await waitFor(() => expect(screen.getByText('Improved')).toBeTruthy())
  })

  it('shows close button when onClose provided', async () => {
    compareRuns.mockRejectedValue(new Error('not implemented'))
    const onClose = vi.fn()
    const runA = { id: 1, duration_seconds: 100, status: 'stopped' }
    const runB = { id: 2, duration_seconds: 100, status: 'stopped' }
    wrap(<RunComparison runA={runA} runB={runB} onClose={onClose} />)
    await waitFor(() => expect(screen.getByLabelText('Close comparison')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('Close comparison'))
    expect(onClose).toHaveBeenCalled()
  })
})

// --- DirectivePanel ---
describe('DirectivePanel', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getDirectiveStatus.mockResolvedValue({ pending: false })
  })

  it('renders with agent name', () => {
    wrap(<DirectivePanel projectId={1} agentName="Claude-1" />)
    expect(screen.getByText('Direct Claude-1')).toBeTruthy()
  })

  it('sends directive on button click', async () => {
    sendDirective.mockResolvedValue({ status: 'queued' })
    wrap(<DirectivePanel projectId={1} agentName="Claude-1" />)
    const textarea = screen.getByLabelText('Directive text for Claude-1')
    fireEvent.change(textarea, { target: { value: 'Focus on testing' } })
    fireEvent.click(screen.getByText('Send'))
    await waitFor(() => {
      expect(sendDirective).toHaveBeenCalledWith(1, 'Claude-1', 'Focus on testing', 'normal')
    })
  })

  it('supports urgent priority', async () => {
    sendDirective.mockResolvedValue({ status: 'queued' })
    wrap(<DirectivePanel projectId={1} agentName="Claude-2" />)
    fireEvent.click(screen.getByRole('radio', { name: /urgent/i }))

    // Type directive and send
    const textarea = screen.getByLabelText('Directive text for Claude-2')
    fireEvent.change(textarea, { target: { value: 'Critical fix needed' } })
    fireEvent.click(screen.getByText('Send'))
    await waitFor(() => {
      expect(sendDirective).toHaveBeenCalledWith(1, 'Claude-2', 'Critical fix needed', 'urgent')
    })
  })

  it('shows pending indicator when directive is queued', async () => {
    getDirectiveStatus.mockResolvedValue({ pending: true, text: 'Do something' })
    wrap(<DirectivePanel projectId={1} agentName="Claude-1" />)
    await waitFor(() => expect(screen.getByText('Pending')).toBeTruthy())
  })

  it('calls onClose when close button clicked', () => {
    const onClose = vi.fn()
    wrap(<DirectivePanel projectId={1} agentName="Claude-1" onClose={onClose} />)
    fireEvent.click(screen.getByLabelText('Close directive panel'))
    expect(onClose).toHaveBeenCalled()
  })

  it('disables send when text is empty', () => {
    wrap(<DirectivePanel projectId={1} agentName="Claude-1" />)
    const sendBtn = screen.getByText('Send')
    expect(sendBtn.disabled).toBe(true)
  })
})

// --- PromptEditorModal ---
describe('PromptEditorModal', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('does not render when not open', () => {
    const { container } = wrap(
      <PromptEditorModal open={false} projectId={1} agentName="Claude-1" currentPrompt="" onClose={vi.fn()} />
    )
    expect(container.querySelector('[role="dialog"]')).toBeNull()
  })

  it('renders editor when open', () => {
    wrap(
      <PromptEditorModal open={true} projectId={1} agentName="Claude-1" currentPrompt="test prompt" onClose={vi.fn()} />
    )
    expect(screen.getByText('Edit Prompt')).toBeTruthy()
    expect(screen.getByText('Claude-1')).toBeTruthy()
    expect(screen.getByLabelText('Prompt content for Claude-1')).toBeTruthy()
  })

  it('saves prompt on Save click', async () => {
    updateAgentPrompt.mockResolvedValue({ old_prompt: 'old' })
    const onClose = vi.fn()
    wrap(
      <PromptEditorModal open={true} projectId={1} agentName="Claude-1" currentPrompt="old" onClose={onClose} />
    )
    const textarea = screen.getByLabelText('Prompt content for Claude-1')
    fireEvent.change(textarea, { target: { value: 'new prompt' } })
    fireEvent.click(screen.getByText('Save'))
    await waitFor(() => {
      expect(updateAgentPrompt).toHaveBeenCalledWith(1, 'Claude-1', 'new prompt')
    })
  })

  it('saves and restarts on Save & Restart click', async () => {
    updateAgentPrompt.mockResolvedValue({ old_prompt: 'old' })
    restartAgent.mockResolvedValue({})
    const onClose = vi.fn()
    wrap(
      <PromptEditorModal open={true} projectId={1} agentName="Claude-2" currentPrompt="old" onClose={onClose} />
    )
    const textarea = screen.getByLabelText('Prompt content for Claude-2')
    fireEvent.change(textarea, { target: { value: 'updated prompt' } })
    fireEvent.click(screen.getByText('Save & Restart'))
    await waitFor(() => {
      expect(updateAgentPrompt).toHaveBeenCalledWith(1, 'Claude-2', 'updated prompt')
      expect(restartAgent).toHaveBeenCalledWith(1, 'Claude-2')
    })
  })

  it('disables Save when no changes', () => {
    wrap(
      <PromptEditorModal open={true} projectId={1} agentName="Claude-1" currentPrompt="test" onClose={vi.fn()} />
    )
    expect(screen.getByText('Save').disabled).toBe(true)
  })

  it('calls onClose when Cancel clicked', () => {
    const onClose = vi.fn()
    wrap(
      <PromptEditorModal open={true} projectId={1} agentName="Claude-1" currentPrompt="" onClose={onClose} />
    )
    fireEvent.click(screen.getByText('Cancel'))
    expect(onClose).toHaveBeenCalled()
  })
})

// --- SwarmHistory with comparison ---
describe('SwarmHistory with comparison', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows compare hint when 2+ runs', async () => {
    const fetchHistory = vi.fn().mockResolvedValue({
      runs: [
        { id: 1, started_at: '2024-01-01T12:00:00Z', duration_seconds: 100, status: 'stopped', tasks_completed: 5 },
        { id: 2, started_at: '2024-01-01T13:00:00Z', duration_seconds: 200, status: 'stopped', tasks_completed: 10 },
      ]
    })
    wrap(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    await waitFor(() => expect(screen.getByText('Select 2 runs to compare')).toBeTruthy())
  })

  it('enables Compare button when 2 runs selected', async () => {
    const fetchHistory = vi.fn().mockResolvedValue({
      runs: [
        { id: 1, started_at: '2024-01-01T12:00:00Z', duration_seconds: 100, status: 'stopped', tasks_completed: 5 },
        { id: 2, started_at: '2024-01-01T13:00:00Z', duration_seconds: 200, status: 'stopped', tasks_completed: 10 },
      ]
    })
    wrap(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    await waitFor(() => expect(screen.getAllByRole('checkbox')).toHaveLength(2))

    const checkboxes = screen.getAllByRole('checkbox')
    fireEvent.click(checkboxes[0])
    fireEvent.click(checkboxes[1])
    await waitFor(() => expect(screen.getByText('Compare (2)')).toBeTruthy())
  })
})

// --- SwarmControls with broadcast ---
describe('SwarmControls broadcast directive', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('shows Direct All button when running with alive agents', () => {
    const agents = [{ name: 'Claude-1', alive: true }, { name: 'Claude-2', alive: true }]
    wrap(<SwarmControls projectId={1} status="running" config={{}} onAction={vi.fn()} agents={agents} />)
    expect(screen.getByText('Direct All')).toBeTruthy()
  })

  it('does not show Direct All when no alive agents', () => {
    const agents = [{ name: 'Claude-1', alive: false }]
    wrap(<SwarmControls projectId={1} status="running" config={{}} onAction={vi.fn()} agents={agents} />)
    expect(screen.queryByText('Direct All')).toBeNull()
  })

  it('opens broadcast panel on Direct All click', () => {
    const agents = [{ name: 'Claude-1', alive: true }]
    wrap(<SwarmControls projectId={1} status="running" config={{}} onAction={vi.fn()} agents={agents} />)
    fireEvent.click(screen.getByText('Direct All'))
    expect(screen.getByText('Direct All Agents')).toBeTruthy()
    expect(screen.getByLabelText('Broadcast directive text')).toBeTruthy()
  })

  it('sends broadcast to all alive agents', async () => {
    sendDirective.mockResolvedValue({})
    const agents = [
      { name: 'Claude-1', alive: true },
      { name: 'Claude-2', alive: true },
      { name: 'Claude-3', alive: false },
    ]
    wrap(<SwarmControls projectId={1} status="running" config={{}} onAction={vi.fn()} agents={agents} />)
    fireEvent.click(screen.getByText('Direct All'))

    const textarea = screen.getByLabelText('Broadcast directive text')
    fireEvent.change(textarea, { target: { value: 'Focus on tests' } })
    fireEvent.click(screen.getByText('Send to All'))

    await waitFor(() => {
      expect(sendDirective).toHaveBeenCalledTimes(2) // Only alive agents
      expect(sendDirective).toHaveBeenCalledWith(1, 'Claude-1', 'Focus on tests', 'normal')
      expect(sendDirective).toHaveBeenCalledWith(1, 'Claude-2', 'Focus on tests', 'normal')
    })
  })
})

// --- AgentGrid with directive indicators ---
describe('AgentGrid directive indicators', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getDirectiveStatus.mockResolvedValue({ pending: false })
  })

  it('renders agents with edit prompt button', () => {
    const agents = [{ name: 'Claude-1', last_heartbeat: new Date().toISOString() }]
    const processAgents = [{ name: 'Claude-1', alive: true, pid: 1234 }]
    wrap(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
    expect(screen.getByLabelText('Edit prompt for Claude-1')).toBeTruthy()
  })

  it('shows pending directive indicator', async () => {
    getDirectiveStatus.mockResolvedValue({ pending: true })
    const agents = [{ name: 'Claude-1', last_heartbeat: new Date().toISOString() }]
    const processAgents = [{ name: 'Claude-1', alive: true, pid: 1234 }]
    wrap(<AgentGrid agents={agents} processAgents={processAgents} projectId={1} />)
    await waitFor(() => {
      expect(screen.getByTitle('Directive pending')).toBeTruthy()
    })
  })
})
