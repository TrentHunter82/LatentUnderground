import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'

// Mock react-router-dom
vi.mock('react-router-dom', () => ({
  useNavigate: () => vi.fn(),
  useParams: () => ({ id: '1' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}))

// Mock api module with all functions ProjectView needs
vi.mock('../lib/api', () => ({
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test', goal: 'Test goal', config: null })),
  getSwarmStatus: vi.fn(() => Promise.resolve(null)),
  getProjectStats: vi.fn(() => Promise.resolve(null)),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
  updateProjectConfig: vi.fn(),
  deleteProject: vi.fn(),
  startWatch: vi.fn(() => Promise.resolve()),
  launchSwarm: vi.fn(),
  stopSwarm: vi.fn(),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  createProject: vi.fn(),
  getTemplates: vi.fn(() => Promise.resolve([])),
}))

import { getSwarmHistory } from '../lib/api'
import { ToastProvider } from '../components/Toast'
import ProjectView from '../components/ProjectView'
import Dashboard from '../components/Dashboard'
import Sparkline from '../components/Sparkline'

function renderProjectView(props = {}) {
  return render(
    <ToastProvider>
      <ProjectView wsEvents={null} onProjectChange={vi.fn()} {...props} />
    </ToastProvider>
  )
}

// --- Keyboard Navigation for Tabs ---
describe('ProjectView tab keyboard navigation', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders all tab buttons with correct ARIA attributes', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')
    expect(tabs).toHaveLength(6)

    // First tab (Dashboard) should be selected
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[0]).toHaveAttribute('tabindex', '0')

    // Other tabs should not be selected
    for (let i = 1; i < tabs.length; i++) {
      expect(tabs[i]).toHaveAttribute('aria-selected', 'false')
      expect(tabs[i]).toHaveAttribute('tabindex', '-1')
    }
  })

  it('moves to next tab on ArrowRight', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')

    fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })

    // History tab should now be selected
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')
    expect(tabs[1]).toHaveAttribute('tabindex', '0')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'false')
  })

  it('moves to previous tab on ArrowLeft', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')

    // First click History tab to select it
    fireEvent.click(tabs[1])
    expect(tabs[1]).toHaveAttribute('aria-selected', 'true')

    // Then ArrowLeft back to Dashboard
    fireEvent.keyDown(tabs[1], { key: 'ArrowLeft' })
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('wraps from last to first on ArrowRight', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')

    // Select last tab (Settings)
    fireEvent.click(tabs[5])
    expect(tabs[5]).toHaveAttribute('aria-selected', 'true')

    // ArrowRight should wrap to first (Dashboard)
    fireEvent.keyDown(tabs[5], { key: 'ArrowRight' })
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('wraps from first to last on ArrowLeft', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')

    // ArrowLeft from first tab should go to last
    fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' })
    expect(tabs[5]).toHaveAttribute('aria-selected', 'true')
  })

  it('jumps to first tab on Home', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')

    // Select a middle tab first
    fireEvent.click(tabs[3])
    expect(tabs[3]).toHaveAttribute('aria-selected', 'true')

    // Home should go to first tab
    fireEvent.keyDown(tabs[3], { key: 'Home' })
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })

  it('jumps to last tab on End', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')

    // End should go to last tab
    fireEvent.keyDown(tabs[0], { key: 'End' })
    expect(tabs[5]).toHaveAttribute('aria-selected', 'true')
  })

  it('tabpanel has aria-labelledby linking to active tab', async () => {
    await act(async () => { renderProjectView() })
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveAttribute('aria-labelledby', 'tab-dashboard')

    // Switch tab and verify link updates
    const tabs = screen.getAllByRole('tab')
    fireEvent.click(tabs[1])
    const updatedPanel = screen.getByRole('tabpanel')
    expect(updatedPanel).toHaveAttribute('aria-labelledby', 'tab-history')
  })

  it('ignores non-navigation keys', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')

    // Press a regular key - should not change tab
    fireEvent.keyDown(tabs[0], { key: 'a' })
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')
  })
})

// --- Project Export Button ---
// jsdom doesn't implement scrollIntoView
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = vi.fn()
}

function renderDashboard(props = {}) {
  return render(
    <ToastProvider>
      <Dashboard wsEvents={null} onProjectChange={vi.fn()} {...props} />
    </ToastProvider>
  )
}

describe('Dashboard export button', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('renders export button with download icon', async () => {
    await act(async () => { renderDashboard() })
    const exportBtn = screen.getByTitle('Export project')
    expect(exportBtn).toBeInTheDocument()
    expect(exportBtn.tagName).toBe('BUTTON')
  })

  it('calls getSwarmHistory on export click', async () => {
    // Mock URL methods for Blob download
    const origCreate = URL.createObjectURL
    const origRevoke = URL.revokeObjectURL
    URL.createObjectURL = vi.fn(() => 'blob:test')
    URL.revokeObjectURL = vi.fn()

    await act(async () => { renderDashboard() })

    await act(async () => {
      fireEvent.click(screen.getByTitle('Export project'))
    })

    expect(getSwarmHistory).toHaveBeenCalledWith(1)
    expect(URL.createObjectURL).toHaveBeenCalled()

    URL.createObjectURL = origCreate
    URL.revokeObjectURL = origRevoke
  })
})

// --- Sparkline Component ---
describe('Sparkline', () => {
  it('renders SVG with polyline for multiple data points', () => {
    const { container } = render(<Sparkline data={[1, 3, 2, 5, 4]} />)
    const svg = container.querySelector('svg')
    expect(svg).toBeInTheDocument()
    expect(svg).toHaveAttribute('role', 'img')
    expect(svg).toHaveAttribute('aria-label', 'Sparkline: 5 points')
    const polyline = container.querySelector('polyline')
    expect(polyline).toBeInTheDocument()
    expect(polyline).toHaveAttribute('points')
  })

  it('renders placeholder line for empty data', () => {
    const { container } = render(<Sparkline data={[]} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('aria-label', 'Sparkline: no data')
    const line = container.querySelector('line')
    expect(line).toBeInTheDocument()
    expect(container.querySelector('polyline')).toBeNull()
  })

  it('renders dot for single data point', () => {
    const { container } = render(<Sparkline data={[42]} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('aria-label', 'Sparkline: 1 point')
    const circle = container.querySelector('circle')
    expect(circle).toBeInTheDocument()
    expect(container.querySelector('polyline')).toBeNull()
  })
})
