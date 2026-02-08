/**
 * Accessibility tests for Latent Underground components.
 *
 * Tests ARIA attributes, keyboard navigation, screen reader compatibility,
 * and semantic HTML across key interactive components.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor, within } from '@testing-library/react'

// ============================================================
// ConfirmDialog - ARIA alertdialog, focus trap, keyboard nav
// ============================================================
import ConfirmDialog from '../components/ConfirmDialog'

describe('ConfirmDialog Accessibility', () => {
  it('has role="alertdialog" when open', () => {
    render(
      <ConfirmDialog open={true} title="Test" message="Msg" onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
  })

  it('has aria-modal="true"', () => {
    render(
      <ConfirmDialog open={true} title="Test" message="Msg" onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    expect(screen.getByRole('alertdialog')).toHaveAttribute('aria-modal', 'true')
  })

  it('has aria-labelledby pointing to title', () => {
    render(
      <ConfirmDialog open={true} title="Confirm Delete" message="Are you sure?" onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveAttribute('aria-labelledby', 'confirm-dialog-title')
    expect(document.getElementById('confirm-dialog-title')).toHaveTextContent('Confirm Delete')
  })

  it('has aria-describedby pointing to message', () => {
    render(
      <ConfirmDialog open={true} title="Title" message="Detailed message here" onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    const dialog = screen.getByRole('alertdialog')
    expect(dialog).toHaveAttribute('aria-describedby', 'confirm-dialog-message')
    expect(document.getElementById('confirm-dialog-message')).toHaveTextContent('Detailed message here')
  })

  it('does not render when closed', () => {
    render(
      <ConfirmDialog open={false} title="T" message="M" onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
  })

  it('closes on Escape key', () => {
    const onCancel = vi.fn()
    render(
      <ConfirmDialog open={true} title="T" message="M" onConfirm={vi.fn()} onCancel={onCancel} />
    )
    fireEvent.keyDown(screen.getByRole('alertdialog'), { key: 'Escape' })
    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it('renders both confirm and cancel buttons', () => {
    render(
      <ConfirmDialog
        open={true}
        title="T"
        message="M"
        confirmLabel="Yes"
        cancelLabel="No"
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText('Yes')).toBeInTheDocument()
    expect(screen.getByText('No')).toBeInTheDocument()
  })
})

// ============================================================
// TaskProgress - progressbar role, aria-value attributes
// ============================================================
import TaskProgress from '../components/TaskProgress'

describe('TaskProgress Accessibility', () => {
  it('has role="progressbar"', () => {
    render(<TaskProgress tasks={{ total: 10, done: 5, percent: 50 }} />)
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('has correct aria-valuenow', () => {
    render(<TaskProgress tasks={{ total: 10, done: 7, percent: 70 }} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '70')
  })

  it('has aria-valuemin=0 and aria-valuemax=100', () => {
    render(<TaskProgress tasks={{ total: 10, done: 5, percent: 50 }} />)
    const bar = screen.getByRole('progressbar')
    expect(bar).toHaveAttribute('aria-valuemin', '0')
    expect(bar).toHaveAttribute('aria-valuemax', '100')
  })

  it('has descriptive aria-label', () => {
    render(<TaskProgress tasks={{ total: 8, done: 3, percent: 37.5 }} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute(
      'aria-label',
      'Task progress: 3 of 8 complete'
    )
  })

  it('aria-valuenow is 0 for empty tasks', () => {
    render(<TaskProgress tasks={{ total: 0, done: 0, percent: 0 }} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '0')
  })

  it('aria-valuenow is 100 when all tasks done', () => {
    render(<TaskProgress tasks={{ total: 5, done: 5, percent: 100 }} />)
    expect(screen.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '100')
  })
})

// ============================================================
// ThemeToggle - aria-label, button semantics
// ============================================================
import ThemeToggle from '../components/ThemeToggle'
import { ThemeProvider } from '../hooks/useTheme.jsx'

describe('ThemeToggle Accessibility', () => {
  it('renders as a button element', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    )
    // Default theme is 'dark', so label should say "Switch to light mode"
    const btn = screen.getByRole('button', { name: /switch to light mode/i })
    expect(btn).toBeInTheDocument()
  })

  it('has matching aria-label and title', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    )
    const btn = screen.getByRole('button')
    const ariaLabel = btn.getAttribute('aria-label')
    const title = btn.getAttribute('title')
    expect(ariaLabel).toBe(title)
  })

  it('aria-label updates after toggle', () => {
    render(
      <ThemeProvider>
        <ThemeToggle />
      </ThemeProvider>
    )
    const btn = screen.getByRole('button')
    expect(btn).toHaveAttribute('aria-label', 'Switch to light mode')

    fireEvent.click(btn)
    expect(btn).toHaveAttribute('aria-label', 'Switch to dark mode')
  })
})

// ============================================================
// ProjectView tabs - tablist, tab, tabpanel ARIA pattern
// ============================================================
// We need to mock dependencies for ProjectView
vi.mock('react-router-dom', () => ({
  useParams: () => ({ id: '1' }),
  Link: ({ children, to, ...props }) => <a href={to} {...props}>{children}</a>,
  useNavigate: () => vi.fn(),
}))

vi.mock('../lib/api', () => ({
  getProject: vi.fn(() => Promise.resolve({ id: 1, name: 'Test', config: '{}' })),
  getSwarmHistory: vi.fn(() => Promise.resolve({ runs: [] })),
  getSwarmOutput: vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 })),
  updateProjectConfig: vi.fn(),
  getSwarmStatus: vi.fn(() => Promise.resolve({ status: 'created', agents: [], signals: {}, tasks: { total: 0, done: 0, percent: 0 }, phase: null })),
  getProjectStats: vi.fn(() => Promise.resolve({ total_runs: 0, avg_duration_seconds: null, total_tasks_completed: 0 })),
  getLogs: vi.fn(() => Promise.resolve({ logs: [] })),
  getProjects: vi.fn(() => Promise.resolve([])),
  createProject: vi.fn(),
  launchSwarm: vi.fn(),
  stopSwarm: vi.fn(),
  deleteProject: vi.fn(),
  readFile: vi.fn(() => Promise.resolve({ content: '' })),
  writeFile: vi.fn(),
  startWatch: vi.fn(() => Promise.resolve()),
  getTemplates: vi.fn(() => Promise.resolve([])),
}))

import ProjectView from '../components/ProjectView'

function renderProjectView() {
  return render(
    <ToastProvider>
      <ProjectView wsEvents={[]} onProjectChange={vi.fn()} />
    </ToastProvider>
  )
}

describe('ProjectView Tab Accessibility', () => {
  it('has role="tablist" container', async () => {
    await act(async () => { renderProjectView() })
    expect(screen.getByRole('tablist')).toBeInTheDocument()
  })

  it('tablist has aria-label', async () => {
    await act(async () => { renderProjectView() })
    expect(screen.getByRole('tablist')).toHaveAttribute('aria-label', 'Project views')
  })

  it('each tab has role="tab"', async () => {
    await act(async () => { renderProjectView() })
    const tabs = screen.getAllByRole('tab')
    expect(tabs.length).toBe(6) // Dashboard, History, Output, Files, Logs, Settings
  })

  it('active tab has aria-selected="true"', async () => {
    await act(async () => { renderProjectView() })
    const dashboardTab = screen.getByRole('tab', { name: 'Dashboard' })
    expect(dashboardTab).toHaveAttribute('aria-selected', 'true')

    // Other tabs should be aria-selected="false"
    const historyTab = screen.getByRole('tab', { name: 'History' })
    expect(historyTab).toHaveAttribute('aria-selected', 'false')
  })

  it('tabs have aria-controls pointing to tabpanel', async () => {
    await act(async () => { renderProjectView() })
    const dashboardTab = screen.getByRole('tab', { name: 'Dashboard' })
    expect(dashboardTab).toHaveAttribute('aria-controls', 'tabpanel-dashboard')
  })

  it('tabpanel has role="tabpanel"', async () => {
    await act(async () => { renderProjectView() })
    expect(screen.getByRole('tabpanel')).toBeInTheDocument()
  })

  it('tabpanel id matches active tab aria-controls', async () => {
    await act(async () => { renderProjectView() })
    const panel = screen.getByRole('tabpanel')
    expect(panel).toHaveAttribute('id', 'tabpanel-dashboard')
  })

  it('switching tabs updates aria-selected and tabpanel id', async () => {
    await act(async () => { renderProjectView() })

    // Click History tab
    const historyTab = screen.getByRole('tab', { name: 'History' })
    await act(async () => {
      fireEvent.click(historyTab)
    })

    expect(historyTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: 'Dashboard' })).toHaveAttribute('aria-selected', 'false')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'tabpanel-history')
  })
})

// ============================================================
// Sidebar - landmarks, delete button aria-label
// ============================================================
import Sidebar from '../components/Sidebar'
import { ToastProvider } from '../components/Toast'

function renderSidebar(props = {}) {
  const defaults = {
    projects: [
      { id: 1, name: 'Alpha', goal: 'Build alpha', status: 'running' },
      { id: 2, name: 'Beta', goal: 'Build beta', status: 'stopped' },
    ],
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

describe('Sidebar Accessibility', () => {
  it('renders as an aside landmark', () => {
    renderSidebar()
    // <aside> maps to complementary role
    const aside = document.querySelector('aside')
    expect(aside).toBeInTheDocument()
  })

  it('delete buttons have aria-label with project name', () => {
    renderSidebar()
    expect(screen.getByLabelText('Delete Alpha')).toBeInTheDocument()
    expect(screen.getByLabelText('Delete Beta')).toBeInTheDocument()
  })

  it('delete button is a button element', () => {
    renderSidebar()
    const deleteBtn = screen.getByLabelText('Delete Alpha')
    expect(deleteBtn.tagName).toBe('BUTTON')
  })

  it('project links are navigable', () => {
    renderSidebar()
    const links = screen.getAllByRole('link')
    // Should have: branding link + 2 project links
    expect(links.length).toBeGreaterThanOrEqual(3)
  })

  it('new project button is present and clickable', () => {
    renderSidebar()
    const btn = screen.getByText('+ New Project')
    expect(btn.tagName).toBe('BUTTON')
  })

  it('shows empty state text', () => {
    renderSidebar({ projects: [] })
    expect(screen.getByText('No projects yet')).toBeInTheDocument()
  })
})

// ============================================================
// NewProject - form labels, required attributes
// ============================================================
import NewProject from '../components/NewProject'

describe('NewProject Form Accessibility', () => {
  it('all inputs have associated labels', () => {
    render(<NewProject onProjectChange={vi.fn()} />)
    // Check that labels exist for major fields
    expect(screen.getByText('Project Name')).toBeInTheDocument()
    expect(screen.getByText('Goal')).toBeInTheDocument()
    expect(screen.getByText('Project Type')).toBeInTheDocument()
    expect(screen.getByText('Tech Stack')).toBeInTheDocument()
    expect(screen.getByText('Complexity')).toBeInTheDocument()
    expect(screen.getByText('Requirements')).toBeInTheDocument()
    expect(screen.getByText('Project Folder Path')).toBeInTheDocument()
  })

  it('required fields have required attribute', () => {
    render(<NewProject onProjectChange={vi.fn()} />)
    const nameInput = screen.getByPlaceholderText('My Awesome App')
    expect(nameInput).toHaveAttribute('required')

    const goalInput = screen.getByPlaceholderText('What should this project accomplish?')
    expect(goalInput).toHaveAttribute('required')

    const pathInput = screen.getByPlaceholderText('C:/Projects/my-app')
    expect(pathInput).toHaveAttribute('required')
  })

  it('submit button is a button element', () => {
    render(<NewProject onProjectChange={vi.fn()} />)
    const btn = screen.getByText('Create Project')
    expect(btn.tagName).toBe('BUTTON')
    expect(btn).toHaveAttribute('type', 'submit')
  })

  it('complexity options are buttons', () => {
    render(<NewProject onProjectChange={vi.fn()} />)
    const simpleBtn = screen.getByText('Simple')
    const mediumBtn = screen.getByText('Medium')
    const complexBtn = screen.getByText('Complex')
    expect(simpleBtn.tagName).toBe('BUTTON')
    expect(mediumBtn.tagName).toBe('BUTTON')
    expect(complexBtn.tagName).toBe('BUTTON')
  })

  it('complexity buttons have type="button" to prevent form submit', () => {
    render(<NewProject onProjectChange={vi.fn()} />)
    const simpleBtn = screen.getByText('Simple')
    expect(simpleBtn).toHaveAttribute('type', 'button')
  })

  it('buttons are disabled during loading', async () => {
    // Mock createProject to hang
    const { createProject } = await import('../lib/api')
    createProject.mockImplementation(() => new Promise(() => {}))

    render(<NewProject onProjectChange={vi.fn()} />)

    // Fill required fields
    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'Goal' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'C:/test' } })

    // Submit form
    fireEvent.submit(screen.getByText('Create Project').closest('form'))

    await waitFor(() => {
      expect(screen.getByText('Creating...')).toBeDisabled()
    })
  })
})

// ============================================================
// SwarmControls - button semantics, disabled state
// ============================================================
import SwarmControls from '../components/SwarmControls'

function renderSwarmControls(props = {}) {
  const defaults = {
    projectId: 1,
    status: 'created',
    onAction: vi.fn(),
  }
  return render(
    <ToastProvider>
      <SwarmControls {...defaults} {...props} />
    </ToastProvider>
  )
}

describe('SwarmControls Accessibility', () => {
  it('renders Launch button when not running', () => {
    renderSwarmControls({ status: 'created' })
    const btn = screen.getByText('Launch')
    expect(btn.tagName).toBe('BUTTON')
  })

  it('renders Stop button when running', () => {
    renderSwarmControls({ status: 'running' })
    const btn = screen.getByText('Stop Swarm')
    expect(btn.tagName).toBe('BUTTON')
  })

  it('shows Resume button when stopped', () => {
    renderSwarmControls({ status: 'stopped' })
    expect(screen.getByText('Resume')).toBeInTheDocument()
    expect(screen.getByText('Launch')).toBeInTheDocument()
  })

  it('buttons have disabled attribute when loading', async () => {
    const { launchSwarm } = await import('../lib/api')
    launchSwarm.mockImplementation(() => new Promise(() => {}))

    renderSwarmControls({ status: 'created' })
    fireEvent.click(screen.getByText('Launch'))

    await waitFor(() => {
      expect(screen.getByText('Launching...')).toBeDisabled()
    })
  })
})

// ============================================================
// TerminalOutput - log role for live region
// ============================================================
import TerminalOutput from '../components/TerminalOutput'

describe('TerminalOutput Accessibility', () => {
  it('has role="log" for screen reader live region', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
    })
    expect(screen.getByRole('log')).toBeInTheDocument()
  })
})
