import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: '1' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}))

const { createApiMock, TestQueryWrapper } = await vi.hoisted(() => import('./test-utils'))

// Mock api module with ALL exports (including Phase 22 additions)
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
  // Phase 22 additions
  getSystemInfo: vi.fn(() => Promise.resolve({
    cpu_percent: 45.2,
    memory_percent: 62.1,
    disk_percent: 38.5,
    uptime_seconds: 3600,
    python_version: '3.12.0',
    cpu_count: 8,
    db_size_bytes: 1048576,
  })),
  getSystemHealth: vi.fn(() => Promise.resolve({
    status: 'ok',
    db: { schema_version: 4 },
    active_processes: 2,
  })),
  getMetrics: vi.fn(() => Promise.resolve('')),
  getHealthTrends: vi.fn(() => Promise.resolve({})),
  getProjectHealth: vi.fn(() => Promise.resolve({
    crash_rate: 5,
    trend: 'stable',
    classification: 'healthy',
    total_runs: 10,
  })),
  getProjectQuota: vi.fn(() => Promise.resolve({
    agent_count: 2,
    elapsed_hours: 1.5,
    max_restart_count: 1,
  })),
  getRunCheckpoints: vi.fn(() => Promise.resolve([])),
}))

import {
  getSystemInfo, getSystemHealth, getProjectHealth, getProjectQuota, getRunCheckpoints, getSwarmHistory,
} from '../lib/api'
import { ToastProvider } from '../components/Toast'
import OperationsDashboard from '../components/OperationsDashboard'
import CheckpointTimeline from '../components/CheckpointTimeline'
import ProjectHealthCard from '../components/ProjectHealthCard'
import ProjectSettings from '../components/ProjectSettings'

function wrap(ui) {
  return render(<TestQueryWrapper><ToastProvider>{ui}</ToastProvider></TestQueryWrapper>)
}

// --- OperationsDashboard ---
describe('OperationsDashboard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    // Re-set default implementations after clearAllMocks
    getSystemInfo.mockResolvedValue({
      cpu_percent: 45.2,
      memory_percent: 62.1,
      disk_percent: 38.5,
      uptime_seconds: 3600,
      python_version: '3.12.0',
      cpu_count: 8,
      db_size_bytes: 1048576,
    })
    getSystemHealth.mockResolvedValue({
      status: 'ok',
      db: { schema_version: 4 },
      active_processes: 2,
    })
    // Mock fetch for /api/metrics (Prometheus text format)
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, text: () => Promise.resolve('') }))
  })

  it('renders loading skeleton initially', () => {
    getSystemInfo.mockReturnValue(new Promise(() => {}))
    getSystemHealth.mockReturnValue(new Promise(() => {}))
    wrap(<OperationsDashboard />)
    // Should show animated skeleton
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('renders system metrics when loaded', async () => {
    wrap(<OperationsDashboard />)
    await waitFor(() => {
      expect(screen.getByText('Operations')).toBeTruthy()
    })
    expect(screen.getByText('System Resources')).toBeTruthy()
    expect(screen.getByText('CPU')).toBeTruthy()
    expect(screen.getByText('Memory')).toBeTruthy()
    expect(screen.getByText('Disk')).toBeTruthy()
  })

  it('renders database section', async () => {
    wrap(<OperationsDashboard />)
    await waitFor(() => expect(screen.getByText('Database')).toBeTruthy())
    expect(screen.getByText('DB Size')).toBeTruthy()
    expect(screen.getByText('Schema Version')).toBeTruthy()
  })

  it('renders request metrics section', async () => {
    wrap(<OperationsDashboard />)
    await waitFor(() => expect(screen.getByText('Request Metrics')).toBeTruthy())
    expect(screen.getByText('Total Requests')).toBeTruthy()
    expect(screen.getByText('Avg Latency')).toBeTruthy()
  })

  it('has a refresh button', async () => {
    wrap(<OperationsDashboard />)
    await waitFor(() => expect(screen.getByText('Operations')).toBeTruthy())
    const refreshBtn = screen.getByLabelText('Refresh operations data')
    expect(refreshBtn).toBeTruthy()
  })

  it('refresh button triggers data re-fetch', async () => {
    wrap(<OperationsDashboard />)
    await waitFor(() => expect(screen.getByText('Operations')).toBeTruthy())
    vi.clearAllMocks()
    getSystemInfo.mockResolvedValue({ cpu_percent: 50 })
    getSystemHealth.mockResolvedValue({ status: 'ok' })
    global.fetch = vi.fn(() => Promise.resolve({ ok: true, text: () => Promise.resolve('') }))

    fireEvent.click(screen.getByLabelText('Refresh operations data'))
    await waitFor(() => expect(getSystemInfo).toHaveBeenCalled())
  })

  it('handles all fetch failures gracefully', async () => {
    // Promise.allSettled catches individual failures, so error only shows
    // if none of the fetches succeed and a top-level catch fires
    getSystemInfo.mockRejectedValue(new Error('Network error'))
    getSystemHealth.mockRejectedValue(new Error('Network error'))
    global.fetch = vi.fn(() => Promise.reject(new Error('Network error')))
    wrap(<OperationsDashboard />)
    // Should eventually render (may show partial data or error)
    await waitFor(() => {
      // The component should still render even if data is missing
      expect(screen.getByText('Operations')).toBeTruthy()
    })
  })

  it('formats uptime correctly', async () => {
    getSystemInfo.mockResolvedValue({ uptime_seconds: 90000 })
    wrap(<OperationsDashboard />)
    await waitFor(() => expect(screen.getByText('Uptime')).toBeTruthy())
    expect(screen.getByText('1d 1h')).toBeTruthy()
  })

  it('formats DB size in MB', async () => {
    getSystemInfo.mockResolvedValue({ db_size_bytes: 5242880 })
    getSystemHealth.mockResolvedValue({ status: 'ok' })
    wrap(<OperationsDashboard />)
    await waitFor(() => expect(screen.getByText('5.0 MB')).toBeTruthy())
  })

  it('gauge bars have correct ARIA attributes', async () => {
    wrap(<OperationsDashboard />)
    await waitFor(() => expect(screen.getByText('CPU')).toBeTruthy())
    const gauges = screen.getAllByRole('progressbar')
    expect(gauges.length).toBeGreaterThanOrEqual(3)
    const cpuGauge = gauges.find(g => g.getAttribute('aria-label')?.includes('CPU'))
    expect(cpuGauge).toBeTruthy()
  })
})

// --- CheckpointTimeline ---
describe('CheckpointTimeline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getRunCheckpoints.mockResolvedValue([])
  })

  it('returns null when no runId', () => {
    wrap(<CheckpointTimeline runId={null} />)
    // Component should not render checkpoint-related content
    expect(screen.queryByText('Checkpoints')).toBeNull()
  })

  it('shows loading skeleton', () => {
    getRunCheckpoints.mockReturnValue(new Promise(() => {}))
    wrap(<CheckpointTimeline runId={1} />)
    const skeletons = document.querySelectorAll('.animate-pulse')
    expect(skeletons.length).toBeGreaterThan(0)
  })

  it('shows empty state when no checkpoints', async () => {
    getRunCheckpoints.mockResolvedValue([])
    wrap(<CheckpointTimeline runId={1} />)
    await waitFor(() => {
      expect(screen.getByText(/No checkpoints recorded/)).toBeTruthy()
    })
  })

  it('renders checkpoint markers', async () => {
    getRunCheckpoints.mockResolvedValue([
      { id: 1, agent_name: 'Claude-1', checkpoint_type: 'task_complete', timestamp: '2024-01-01T12:00:00Z', data: {} },
      { id: 2, agent_name: 'Claude-1', checkpoint_type: 'error', timestamp: '2024-01-01T12:05:00Z', data: {} },
      { id: 3, agent_name: 'Claude-2', checkpoint_type: 'milestone', timestamp: '2024-01-01T12:03:00Z', data: {} },
    ])
    wrap(<CheckpointTimeline runId={1} />)
    await waitFor(() => {
      expect(screen.getByText('Checkpoints')).toBeTruthy()
    })
    // Should show agent lanes (using getAllByText since names appear in multiple places)
    expect(screen.getAllByText('Claude-1').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Claude-2').length).toBeGreaterThanOrEqual(1)
  })

  it('renders legend with checkpoint types', async () => {
    getRunCheckpoints.mockResolvedValue([
      { id: 1, agent_name: 'Claude-1', checkpoint_type: 'task_complete', timestamp: '2024-01-01T12:00:00Z', data: {} },
    ])
    wrap(<CheckpointTimeline runId={1} />)
    await waitFor(() => expect(screen.getByText('Task Complete')).toBeTruthy())
    expect(screen.getByText('Error')).toBeTruthy()
    expect(screen.getByText('Milestone')).toBeTruthy()
  })

  it('clicking a checkpoint shows detail panel', async () => {
    getRunCheckpoints.mockResolvedValue([
      {
        id: 1,
        agent_name: 'Claude-1',
        checkpoint_type: 'task_complete',
        timestamp: '2024-01-01T12:00:00Z',
        data: { elapsed_time: 120, output_lines: 500, last_lines: ['Line 1', 'Line 2'] },
      },
    ])
    wrap(<CheckpointTimeline runId={1} />)
    await waitFor(() => expect(screen.getByText('Checkpoints')).toBeTruthy())

    // Click the checkpoint marker
    const markers = screen.getAllByRole('button')
    const checkpointBtn = markers.find(b => b.getAttribute('aria-label')?.includes('Task Complete'))
    expect(checkpointBtn).toBeTruthy()
    fireEvent.click(checkpointBtn)

    // Detail panel should appear
    await waitFor(() => {
      expect(screen.getByText('Output Preview:')).toBeTruthy()
    })
    // Check the pre element contains the lines (text is in a pre, may split differently)
    const pre = document.querySelector('pre')
    expect(pre.textContent).toContain('Line 1')
    expect(pre.textContent).toContain('Line 2')
  })

  it('handles 404 gracefully', async () => {
    getRunCheckpoints.mockRejectedValue(new Error('404: Not Found'))
    wrap(<CheckpointTimeline runId={999} />)
    await waitFor(() => {
      expect(screen.getByText(/No checkpoints recorded/)).toBeTruthy()
    })
  })

  it('agent filter dropdown appears with multiple agents', async () => {
    getRunCheckpoints.mockResolvedValue([
      { id: 1, agent_name: 'Claude-1', checkpoint_type: 'task_complete', timestamp: '2024-01-01T12:00:00Z', data: {} },
      { id: 2, agent_name: 'Claude-2', checkpoint_type: 'error', timestamp: '2024-01-01T12:01:00Z', data: {} },
    ])
    wrap(<CheckpointTimeline runId={1} />)
    await waitFor(() => expect(screen.getByText('Checkpoints')).toBeTruthy())
    expect(screen.getByLabelText('Filter checkpoints by agent')).toBeTruthy()
  })
})

// --- ProjectHealthCard ---
describe('ProjectHealthCard', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getProjectHealth.mockResolvedValue({
      crash_rate: 5,
      trend: 'stable',
      classification: 'healthy',
      total_runs: 10,
    })
    getSwarmHistory.mockResolvedValue({ runs: [] })
  })

  it('renders health status', async () => {
    wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => {
      expect(screen.getByText('Project Health')).toBeTruthy()
    })
    expect(screen.getByText('Healthy')).toBeTruthy()
  })

  it('shows crash rate percentage', async () => {
    wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => expect(screen.getByText('Crash Rate')).toBeTruthy())
    expect(screen.getByText('5%')).toBeTruthy()
  })

  it('shows run count', async () => {
    wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => expect(screen.getByText('Runs')).toBeTruthy())
    expect(screen.getByText('10')).toBeTruthy()
  })

  it('renders compact mode', async () => {
    wrap(<ProjectHealthCard projectId={1} compact />)
    await waitFor(() => {
      const healthDot = screen.getByRole('img', { name: /Health/ })
      expect(healthDot).toBeTruthy()
    })
    // Compact mode should NOT show the full card
    expect(screen.queryByText('Project Health')).toBeNull()
  })

  it('handles warning classification', async () => {
    getProjectHealth.mockResolvedValue({
      crash_rate: 20,
      trend: 'degrading',
      classification: 'warning',
      total_runs: 15,
    })
    wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => expect(screen.getByText('Warning')).toBeTruthy())
  })

  it('handles critical classification', async () => {
    getProjectHealth.mockResolvedValue({
      crash_rate: 50,
      trend: 'degrading',
      classification: 'critical',
      total_runs: 8,
    })
    wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => expect(screen.getByText('Critical')).toBeTruthy())
  })

  it('computes health locally when endpoint returns 404', async () => {
    getProjectHealth.mockRejectedValue(new Error('404'))
    getSwarmHistory.mockResolvedValue({
      runs: [
        { id: 1, status: 'completed' },
        { id: 2, status: 'completed' },
        { id: 3, status: 'failed' },
        { id: 4, status: 'completed' },
        { id: 5, status: 'completed' },
      ],
    })
    wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => expect(screen.getByText('Project Health')).toBeTruthy())
    // 1 out of 5 failed = 20% crash rate -> warning
    expect(screen.getByText('Warning')).toBeTruthy()
  })

  it('returns null when no data available', async () => {
    getProjectHealth.mockRejectedValue(new Error('500'))
    getSwarmHistory.mockResolvedValue({ runs: [] })
    const { container } = wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => {
      // Wait for loading to finish
      expect(container.querySelector('.animate-pulse')).toBeNull()
    })
    // No health data + no runs = render nothing
  })

  it('has accessible ARIA labels on health dot', async () => {
    wrap(<ProjectHealthCard projectId={1} />)
    await waitFor(() => expect(screen.getByText('Healthy')).toBeTruthy())
    const dot = screen.getByRole('img', { name: /Health: Healthy/ })
    expect(dot).toBeTruthy()
  })
})

// --- ProjectSettings Quotas ---
describe('ProjectSettings Quotas', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getProjectQuota.mockResolvedValue({
      agent_count: 2,
      elapsed_hours: 1.5,
      max_restart_count: 1,
    })
  })

  it('renders quota section', () => {
    wrap(<ProjectSettings projectId={1} />)
    expect(screen.getByText('Resource Quotas')).toBeTruthy()
  })

  it('renders quota sliders', () => {
    wrap(<ProjectSettings projectId={1} />)
    expect(screen.getByLabelText(/Max Concurrent Agents/)).toBeTruthy()
    expect(screen.getByLabelText(/Max Duration/)).toBeTruthy()
    expect(screen.getByLabelText(/Max Restarts/)).toBeTruthy()
  })

  it('loads initial quota values from config', () => {
    wrap(
      <ProjectSettings
        projectId={1}
        initialConfig={{
          agent_count: 4,
          max_phases: 24,
          max_agents_concurrent: 8,
          max_duration_hours: 12,
          max_restarts_per_agent: 3,
        }}
      />
    )
    // Sliders should reflect initial values
    const agentSlider = screen.getByLabelText(/Max Concurrent Agents: 8/)
    expect(agentSlider).toBeTruthy()
  })

  it('includes quota values in save', async () => {
    const onSave = vi.fn(() => Promise.resolve({}))
    wrap(
      <ProjectSettings
        projectId={1}
        initialConfig={{
          agent_count: 4,
          max_phases: 24,
          max_agents_concurrent: 5,
          max_duration_hours: null,
          max_restarts_per_agent: null,
        }}
        onSave={onSave}
      />
    )

    // Change agent count to trigger dirty state
    const agentInput = screen.getByLabelText('Agent Count')
    fireEvent.change(agentInput, { target: { value: '3' } })

    // Submit
    const saveBtn = screen.getByText('Save Settings')
    fireEvent.click(saveBtn)

    await waitFor(() => {
      expect(onSave).toHaveBeenCalledWith(1, expect.objectContaining({
        agent_count: 3,
        max_agents_concurrent: 5,
      }))
    })
  })

  it('shows usage bars when quota is set', async () => {
    wrap(
      <ProjectSettings
        projectId={1}
        initialConfig={{
          agent_count: 4,
          max_phases: 24,
          max_agents_concurrent: 5,
          max_duration_hours: 10,
          max_restarts_per_agent: 3,
        }}
      />
    )
    await waitFor(() => {
      // Should show usage like "2/5"
      expect(screen.getByText('2/5')).toBeTruthy()
    })
  })

  it('shows quota helper text', () => {
    wrap(<ProjectSettings projectId={1} />)
    expect(screen.getByText(/Set to max to allow unlimited/)).toBeTruthy()
  })
})
