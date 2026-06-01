/**
 * ProjectWorkspace — dockable workspace orchestration.
 *
 * dockview-react is mocked with an in-memory fake api so we can assert the
 * workspace's OWN logic (default layout, per-project localStorage persistence,
 * restore-on-mount, reset, add-closed-panel) without dockview's real DOM
 * layout/measurement, which doesn't behave in jsdom. The live drag/resize/
 * re-tile behavior is exercised in the running app (and e2e), per TESTING_RULES.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, act, fireEvent, waitFor } from '@testing-library/react'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'
import { createApiMock, createProjectQueryMock, createSwarmQueryMock, createMutationsMock } from './test-utils'
import { AppChromeProvider } from '../hooks/useAppChrome'

expect.extend(matchers)

// In-memory fake dockview: records panels, fires layout-change listeners, and
// round-trips toJSON/fromJSON as a simple { panels: [ids] } shape.
vi.mock('dockview-react', async () => {
  const React = await vi.importActual('react')
  function makeFakeApi() {
    const panels = []
    const listeners = new Set()
    const fire = () => listeners.forEach((l) => l())
    const api = {
      panels,
      addPanel: ({ id, component, title }) => {
        if (panels.some((p) => p.id === id)) return panels.find((p) => p.id === id)
        const panel = { id, component, title, api: { setActive() {}, setSize() {} } }
        panels.push(panel)
        fire()
        return panel
      },
      getPanel: (id) => panels.find((p) => p.id === id),
      clear: () => { panels.length = 0; fire() },
      toJSON: () => ({ panels: panels.map((p) => p.id) }),
      fromJSON: (json) => { (json?.panels || []).forEach((id) => api.addPanel({ id, component: id, title: id })) },
      onDidLayoutChange: (cb) => { listeners.add(cb); return { dispose: () => listeners.delete(cb) } },
    }
    return api
  }
  function DockviewReact({ onReady, className }) {
    const started = React.useRef(false)
    React.useEffect(() => {
      if (started.current) return
      started.current = true
      onReady({ api: makeFakeApi() })
    }, [onReady])
    return React.createElement('div', { 'data-testid': 'dockview', className })
  }
  return { DockviewReact }
})

// Keep panel-component module imports side-effect-free.
vi.mock('../lib/api', () => createApiMock())
vi.mock('../hooks/useProjectQuery', () => createProjectQueryMock())
vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock())
vi.mock('../hooks/useMutations', () => createMutationsMock())

const STORAGE_KEY = 'lu_dock_layout_1'
const ALL_PANELS = ['navigator', 'dashboard', 'output', 'logs', 'history', 'files', 'analytics', 'settings']

async function renderWorkspace(props = {}) {
  const { default: ProjectWorkspace } = await import('../components/ProjectWorkspace')
  return render(
    <AppChromeProvider value={{ projects: [], onRefresh: vi.fn(), projectHealth: {}, showArchived: false, onShowArchivedChange: vi.fn() }}>
      <ProjectWorkspace projectId={1} wsEvents={null} project={{ id: 1, name: 'Demo', status: 'running' }} initialConfig={null} onProjectChange={vi.fn()} {...props} />
    </AppChromeProvider>,
  )
}

describe('ProjectWorkspace — dockable layout', () => {
  beforeEach(() => { localStorage.clear() })

  it('renders the dock surface and the workspace toolbar', async () => {
    await act(async () => { await renderWorkspace() })
    expect(screen.getByTestId('dockview')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /reset layout/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add panel/i })).toBeInTheDocument()
    expect(screen.getByText('Demo')).toBeInTheDocument()
  })

  it('builds the default 8-tile layout and persists it per project', async () => {
    await act(async () => { await renderWorkspace() })
    await waitFor(() => expect(localStorage.getItem(STORAGE_KEY)).toBeTruthy())
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY))
    expect(new Set(saved.panels)).toEqual(new Set(ALL_PANELS))
  })

  it('restores a saved per-project layout instead of the default', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ panels: ['dashboard', 'logs'] }))
    await act(async () => { await renderWorkspace() })
    // Only the two saved panels are open → the rest are offered by "Add panel".
    const addBtn = screen.getByRole('button', { name: /add panel/i })
    expect(addBtn).not.toBeDisabled()
    await act(async () => { fireEvent.click(addBtn) })
    expect(screen.getByRole('menuitem', { name: 'Terminal' })).toBeInTheDocument()
    expect(screen.queryByRole('menuitem', { name: 'Logs' })).not.toBeInTheDocument() // already open
  })

  it('re-adds a closed panel from the Add-panel menu', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ panels: ['dashboard'] }))
    await act(async () => { await renderWorkspace() })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /add panel/i })) })
    await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: 'Analytics' })) })
    // Re-opening Analytics removes it from the closed list.
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /add panel/i })) })
    expect(screen.queryByRole('menuitem', { name: 'Analytics' })).not.toBeInTheDocument()
  })

  it('workspace toolbar has no axe violations', async () => {
    let container
    await act(async () => { ({ container } = await renderWorkspace()) })
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('reset clears the saved layout and restores all default tiles', async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ panels: ['dashboard'] }))
    await act(async () => { await renderWorkspace() })
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: /reset layout/i })) })
    await waitFor(() => {
      const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{"panels":[]}')
      expect(new Set(saved.panels)).toEqual(new Set(ALL_PANELS))
    })
    // With everything open again, Add panel is disabled.
    expect(screen.getByRole('button', { name: /add panel/i })).toBeDisabled()
  })
})
