import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { renderHook } from '@testing-library/react'

// Mock react-router-dom
const mockNavigate = vi.fn()
vi.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useParams: () => ({ id: '1' }),
  Link: ({ to, children, ...props }) => <a href={to} {...props}>{children}</a>,
}))

// Mock api module
vi.mock('../lib/api', () => ({
  getTemplates: vi.fn(() => Promise.resolve([])),
  createProject: vi.fn(() => Promise.resolve({ id: 42, name: 'Test' })),
  launchSwarm: vi.fn(() => Promise.resolve({ status: 'launched' })),
  createTemplate: vi.fn(() => Promise.resolve({ id: 1, name: 'New' })),
  updateTemplate: vi.fn(() => Promise.resolve({ id: 1, name: 'Updated' })),
  deleteTemplate: vi.fn(() => Promise.resolve(null)),
  browseDirectory: vi.fn(() => Promise.resolve({ entries: [] })),
}))

import { getTemplates, createProject, launchSwarm, createTemplate, updateTemplate, deleteTemplate, browseDirectory } from '../lib/api'
import { ToastProvider } from '../components/Toast'
import NewProject from '../components/NewProject'
import TemplateManager from '../components/TemplateManager'
import Sparkline from '../components/Sparkline'
import FolderBrowser from '../components/FolderBrowser'
import { useDebounce } from '../hooks/useDebounce'

function renderNewProject(props = {}) {
  return render(
    <ToastProvider>
      <NewProject onProjectChange={vi.fn()} {...props} />
    </ToastProvider>
  )
}

function renderTemplateManager(props = {}) {
  return render(
    <ToastProvider>
      <TemplateManager onTemplatesChange={vi.fn()} {...props} />
    </ToastProvider>
  )
}

// --- NewProject Template Selector ---
describe('NewProject template selector', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockNavigate.mockClear()
  })

  it('shows "no templates" message when no templates exist', async () => {
    getTemplates.mockResolvedValue([])
    await act(async () => { renderNewProject() })

    // Label always shown, but dropdown is not rendered - shows empty state message instead
    expect(screen.getByText('Start from Template')).toBeInTheDocument()
    expect(screen.getByText(/No templates yet/)).toBeInTheDocument()
    expect(screen.queryByDisplayValue('Custom (no template)')).toBeNull()
  })

  it('shows template dropdown when templates exist', async () => {
    getTemplates.mockResolvedValue([
      { id: 1, name: 'FastAPI Standard', description: '4-agent setup', config: { agent_count: 4, max_phases: 6 } },
    ])
    await act(async () => { renderNewProject() })

    expect(screen.getByText('Start from Template')).toBeInTheDocument()
    expect(screen.getByText(/FastAPI Standard/)).toBeInTheDocument()
  })

  it('populates form fields when template is selected', async () => {
    getTemplates.mockResolvedValue([
      {
        id: 1,
        name: 'React Template',
        description: '',
        config: {
          agent_count: 8,
          max_phases: 12,
          project_type: 'SPA',
          tech_stack: 'React + Vite',
          complexity: 'Complex',
        },
      },
    ])
    await act(async () => { renderNewProject() })

    // Select the template
    const select = screen.getByDisplayValue('Custom (no template)')
    await act(async () => { fireEvent.change(select, { target: { value: '1' } }) })

    // Check form was populated
    const typeInput = screen.getByPlaceholderText('Web Application')
    expect(typeInput.value).toBe('SPA')
    const stackInput = screen.getByPlaceholderText('React + FastAPI + SQLite')
    expect(stackInput.value).toBe('React + Vite')
  })

  it('shows template config info (agents and phases)', async () => {
    getTemplates.mockResolvedValue([
      {
        id: 1,
        name: 'Config Template',
        description: '',
        config: { agent_count: 6, max_phases: 10 },
      },
    ])
    await act(async () => { renderNewProject() })

    const select = screen.getByDisplayValue('Custom (no template)')
    await act(async () => { fireEvent.change(select, { target: { value: '1' } }) })

    expect(screen.getByText(/6 agents/)).toBeInTheDocument()
    expect(screen.getByText(/10 phases/)).toBeInTheDocument()
  })

  it('resets form when deselecting template', async () => {
    getTemplates.mockResolvedValue([
      {
        id: 1,
        name: 'Reset Test',
        description: '',
        config: { project_type: 'CLI Tool', tech_stack: 'Rust' },
      },
    ])
    await act(async () => { renderNewProject() })

    const select = screen.getByDisplayValue('Custom (no template)')
    // Select template
    await act(async () => { fireEvent.change(select, { target: { value: '1' } }) })
    // Deselect (back to custom)
    await act(async () => { fireEvent.change(select, { target: { value: '' } }) })

    const typeInput = screen.getByPlaceholderText('Web Application')
    expect(typeInput.value).toBe('Web Application (frontend + backend)')
  })

  it('submits create project form', async () => {
    getTemplates.mockResolvedValue([])
    createProject.mockResolvedValue({ id: 42, name: 'My App' })

    await act(async () => { renderNewProject() })

    // Fill in required fields
    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'My App' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'Build something' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'F:/MyApp' } })

    // Submit
    await act(async () => {
      fireEvent.click(screen.getByText('Create Project'))
    })

    expect(createProject).toHaveBeenCalledWith(expect.objectContaining({
      name: 'My App',
      goal: 'Build something',
      folder_path: 'F:/MyApp',
    }))
    expect(mockNavigate).toHaveBeenCalledWith('/projects/42')
  })

  it('uses template config for Create & Launch', async () => {
    getTemplates.mockResolvedValue([
      {
        id: 1,
        name: 'Launch Template',
        description: '',
        config: { agent_count: 8, max_phases: 12 },
      },
    ])
    createProject.mockResolvedValue({ id: 55, name: 'Launched' })
    launchSwarm.mockResolvedValue({ status: 'launched' })

    await act(async () => { renderNewProject() })

    // Select template
    const select = screen.getByDisplayValue('Custom (no template)')
    await act(async () => { fireEvent.change(select, { target: { value: '1' } }) })

    // Fill required fields
    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'Launch Test' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'Test' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'F:/Launch' } })

    // Click Create & Launch
    await act(async () => {
      fireEvent.click(screen.getByText('Create & Launch'))
    })

    expect(launchSwarm).toHaveBeenCalledWith(expect.objectContaining({
      project_id: 55,
      agent_count: 8,
      max_phases: 12,
    }))
  })

  it('shows error message on create failure', async () => {
    getTemplates.mockResolvedValue([])
    createProject.mockRejectedValue(new Error('400: Name required'))

    await act(async () => { renderNewProject() })

    fireEvent.change(screen.getByPlaceholderText('My Awesome App'), { target: { value: 'X' } })
    fireEvent.change(screen.getByPlaceholderText('What should this project accomplish?'), { target: { value: 'Y' } })
    fireEvent.change(screen.getByPlaceholderText('C:/Projects/my-app'), { target: { value: 'F:/X' } })

    await act(async () => {
      fireEvent.click(screen.getByText('Create Project'))
    })

    // Error appears in both inline error div and toast notification
    expect(screen.getAllByText('400: Name required').length).toBeGreaterThanOrEqual(1)
  })

  it('renders complexity buttons and allows selection', async () => {
    getTemplates.mockResolvedValue([])
    await act(async () => { renderNewProject() })

    const complexBtn = screen.getByText('Complex')
    fireEvent.click(complexBtn)

    // Complex should now be the active button (has btn-neon class)
    expect(complexBtn.className).toContain('btn-neon')
  })
})


// --- TemplateManager ---
describe('TemplateManager', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('shows empty state when no templates', async () => {
    getTemplates.mockResolvedValue([])
    await act(async () => { renderTemplateManager() })

    expect(screen.getByText('No templates yet')).toBeInTheDocument()
  })

  it('shows list of templates', async () => {
    getTemplates.mockResolvedValue([
      { id: 1, name: 'Template A', description: 'Desc A', config: { agent_count: 4, max_phases: 6 } },
      { id: 2, name: 'Template B', description: '', config: { agent_count: 2, max_phases: 3 } },
    ])
    await act(async () => { renderTemplateManager() })

    expect(screen.getByText('Template A')).toBeInTheDocument()
    expect(screen.getByText('Template B')).toBeInTheDocument()
    expect(screen.getByText('Desc A')).toBeInTheDocument()
    expect(screen.getByText(/4 agents/)).toBeInTheDocument()
  })

  it('opens create form when clicking + New', async () => {
    getTemplates.mockResolvedValue([])
    await act(async () => { renderTemplateManager() })

    fireEvent.click(screen.getByText('+ New'))

    expect(screen.getByText('New Template')).toBeInTheDocument()
    expect(screen.getByPlaceholderText('Template name')).toBeInTheDocument()
  })

  it('creates template on form submit', async () => {
    getTemplates.mockResolvedValueOnce([])
    getTemplates.mockResolvedValueOnce([{ id: 1, name: 'Created', config: {} }])
    createTemplate.mockResolvedValue({ id: 1, name: 'Created' })

    await act(async () => { renderTemplateManager() })

    // Open create form
    fireEvent.click(screen.getByText('+ New'))

    // Fill name
    fireEvent.change(screen.getByPlaceholderText('Template name'), { target: { value: 'Created' } })

    // Save
    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    expect(createTemplate).toHaveBeenCalledWith(expect.objectContaining({ name: 'Created' }))
  })

  it('returns to list view on Cancel', async () => {
    getTemplates.mockResolvedValue([])
    await act(async () => { renderTemplateManager() })

    fireEvent.click(screen.getByText('+ New'))
    expect(screen.getByText('New Template')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Cancel'))
    expect(screen.getByText('No templates yet')).toBeInTheDocument()
  })

  it('has edit and delete buttons for each template', async () => {
    getTemplates.mockResolvedValue([
      { id: 1, name: 'Editable', description: '', config: { agent_count: 4, max_phases: 6 } },
    ])
    await act(async () => { renderTemplateManager() })

    expect(screen.getByLabelText('Edit Editable')).toBeInTheDocument()
    expect(screen.getByLabelText('Delete Editable')).toBeInTheDocument()
  })
})


// --- Sparkline edge cases ---
describe('Sparkline additional tests', () => {
  it('respects custom width and height', () => {
    const { container } = render(<Sparkline data={[1, 2, 3]} width={120} height={40} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('width', '120')
    expect(svg).toHaveAttribute('height', '40')
  })

  it('respects custom color', () => {
    const { container } = render(<Sparkline data={[1, 2, 3]} color="#FF0000" />)
    const polyline = container.querySelector('polyline')
    expect(polyline).toHaveAttribute('stroke', '#FF0000')
  })

  it('handles all-same-value data (zero range)', () => {
    const { container } = render(<Sparkline data={[5, 5, 5, 5]} />)
    const polyline = container.querySelector('polyline')
    expect(polyline).toBeInTheDocument()
    // Should not throw - range=0 is handled by `|| 1`
  })

  it('handles large datasets', () => {
    const data = Array.from({ length: 100 }, (_, i) => i)
    const { container } = render(<Sparkline data={data} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('aria-label', 'Sparkline: 100 points')
  })

  it('uses default dimensions when no props', () => {
    const { container } = render(<Sparkline data={[1, 2]} />)
    const svg = container.querySelector('svg')
    expect(svg).toHaveAttribute('width', '80')
    expect(svg).toHaveAttribute('height', '24')
  })
})


// --- FolderBrowser ---
describe('FolderBrowser', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders nothing when open is false', () => {
    const { container } = render(
      <FolderBrowser open={false} onSelect={vi.fn()} onClose={vi.fn()} />
    )
    expect(container.innerHTML).toBe('')
  })

  it('renders dialog when open is true', async () => {
    browseDirectory.mockResolvedValue({ path: '', parent: null, dirs: [] })
    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })
    expect(screen.getByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('Browse for Folder')).toBeInTheDocument()
  })

  it('shows loading state while browsing', async () => {
    let resolveBrowse
    browseDirectory.mockImplementation(() => new Promise(r => { resolveBrowse = r }))

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })

    expect(screen.getByText('Loading...')).toBeInTheDocument()

    await act(async () => {
      resolveBrowse({ path: 'C:\\', parent: null, dirs: [] })
    })

    expect(screen.queryByText('Loading...')).not.toBeInTheDocument()
  })

  it('displays directory list from API', async () => {
    browseDirectory.mockResolvedValue({
      path: 'C:\\Projects',
      parent: 'C:\\',
      dirs: [
        { name: 'my-app', path: 'C:\\Projects\\my-app' },
        { name: 'other', path: 'C:\\Projects\\other' },
      ],
    })

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })

    expect(screen.getByText('my-app')).toBeInTheDocument()
    expect(screen.getByText('other')).toBeInTheDocument()
  })

  it('shows "No subdirectories" for empty dirs', async () => {
    browseDirectory.mockResolvedValue({ path: 'C:\\Empty', parent: 'C:\\', dirs: [] })

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })

    expect(screen.getByText('No subdirectories')).toBeInTheDocument()
  })

  it('navigates into a subdirectory on click', async () => {
    browseDirectory
      .mockResolvedValueOnce({
        path: 'C:\\',
        parent: null,
        dirs: [{ name: 'Projects', path: 'C:\\Projects' }],
      })
      .mockResolvedValueOnce({
        path: 'C:\\Projects',
        parent: 'C:\\',
        dirs: [{ name: 'my-app', path: 'C:\\Projects\\my-app' }],
      })

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })

    await act(async () => {
      fireEvent.click(screen.getByLabelText('Open folder Projects'))
    })

    expect(browseDirectory).toHaveBeenCalledWith('C:\\Projects')
    expect(screen.getByText('my-app')).toBeInTheDocument()
  })

  it('calls onClose when Close button clicked', async () => {
    browseDirectory.mockResolvedValue({ path: '', parent: null, dirs: [] })
    const onClose = vi.fn()

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={onClose} />)
    })

    fireEvent.click(screen.getByLabelText('Close'))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onClose when Cancel clicked', async () => {
    browseDirectory.mockResolvedValue({ path: '', parent: null, dirs: [] })
    const onClose = vi.fn()

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={onClose} />)
    })

    fireEvent.click(screen.getByText('Cancel'))
    expect(onClose).toHaveBeenCalled()
  })

  it('calls onSelect with selected folder path', async () => {
    browseDirectory.mockResolvedValue({
      path: 'C:\\Projects',
      parent: 'C:\\',
      dirs: [],
    })
    const onSelect = vi.fn()
    const onClose = vi.fn()

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={onSelect} onClose={onClose} />)
    })

    fireEvent.click(screen.getByText('Select Folder'))
    expect(onSelect).toHaveBeenCalledWith('C:\\Projects')
    expect(onClose).toHaveBeenCalled()
  })

  it('appends subfolder name to path on select', async () => {
    browseDirectory.mockResolvedValue({
      path: 'C:\\Projects',
      parent: 'C:\\',
      dirs: [],
    })
    const onSelect = vi.fn()

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={onSelect} onClose={vi.fn()} />)
    })

    // Type subfolder name
    fireEvent.change(screen.getByLabelText('Subfolder name to append to selected path'), {
      target: { value: 'my-app' },
    })

    fireEvent.click(screen.getByText('Select Folder'))
    expect(onSelect).toHaveBeenCalledWith('C:\\Projects/my-app')
  })

  it('shows error message on browse failure', async () => {
    browseDirectory.mockRejectedValue(new Error('Network error'))

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })

    expect(screen.getByText('Network error')).toBeInTheDocument()
  })

  it('disables Select Folder when no path is selected', async () => {
    browseDirectory.mockResolvedValue({ path: '', parent: null, dirs: [] })

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })

    expect(screen.getByText('Select Folder')).toBeDisabled()
  })

  it('disables Go Up button when parent is null', async () => {
    browseDirectory.mockResolvedValue({ path: 'C:\\', parent: null, dirs: [] })

    await act(async () => {
      render(<FolderBrowser open={true} onSelect={vi.fn()} onClose={vi.fn()} />)
    })

    expect(screen.getByLabelText('Go to parent directory')).toBeDisabled()
  })
})


// --- TemplateManager Edit/Delete Flows ---
describe('TemplateManager edit and delete', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('opens edit form with template data', async () => {
    getTemplates.mockResolvedValue([
      { id: 5, name: 'Edit Me', description: 'A desc', config: { agent_count: 8, max_phases: 12 } },
    ])
    await act(async () => { renderTemplateManager() })

    fireEvent.click(screen.getByLabelText('Edit Edit Me'))

    expect(screen.getByText('Edit Template')).toBeInTheDocument()
    expect(screen.getByDisplayValue('Edit Me')).toBeInTheDocument()
    expect(screen.getByDisplayValue('A desc')).toBeInTheDocument()
    expect(screen.getByDisplayValue('8')).toBeInTheDocument()
    expect(screen.getByDisplayValue('12')).toBeInTheDocument()
  })

  it('saves edited template via updateTemplate', async () => {
    getTemplates.mockResolvedValueOnce([
      { id: 5, name: 'Original', description: '', config: { agent_count: 4, max_phases: 6 } },
    ])
    getTemplates.mockResolvedValueOnce([
      { id: 5, name: 'Renamed', description: '', config: { agent_count: 4, max_phases: 6 } },
    ])
    updateTemplate.mockResolvedValue({ id: 5, name: 'Renamed' })

    await act(async () => { renderTemplateManager() })

    fireEvent.click(screen.getByLabelText('Edit Original'))

    // Change name
    fireEvent.change(screen.getByDisplayValue('Original'), { target: { value: 'Renamed' } })

    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    expect(updateTemplate).toHaveBeenCalledWith(5, expect.objectContaining({ name: 'Renamed' }))
  })

  it('opens delete confirmation dialog', async () => {
    getTemplates.mockResolvedValue([
      { id: 3, name: 'Delete This', description: '', config: {} },
    ])
    await act(async () => { renderTemplateManager() })

    fireEvent.click(screen.getByLabelText('Delete Delete This'))

    // ConfirmDialog should show
    expect(screen.getByText(/Delete template "Delete This"/)).toBeInTheDocument()
  })

  it('shows saving state while template saves', async () => {
    getTemplates.mockResolvedValue([])
    let resolveSave
    createTemplate.mockImplementation(() => new Promise(r => { resolveSave = r }))

    await act(async () => { renderTemplateManager() })

    fireEvent.click(screen.getByText('+ New'))
    fireEvent.change(screen.getByPlaceholderText('Template name'), { target: { value: 'Saving Test' } })

    // Don't await the save - check button text changes
    act(() => {
      fireEvent.click(screen.getByText('Save'))
    })

    // Should show Saving... text
    await waitFor(() => {
      expect(screen.getByText('Saving...')).toBeInTheDocument()
    })

    // Resolve the save
    await act(async () => {
      resolveSave({ id: 1, name: 'Saving Test' })
    })
  })

  it('shows error toast on save failure', async () => {
    getTemplates.mockResolvedValue([])
    createTemplate.mockRejectedValue(new Error('Server error'))

    await act(async () => { renderTemplateManager() })

    fireEvent.click(screen.getByText('+ New'))
    fireEvent.change(screen.getByPlaceholderText('Template name'), { target: { value: 'Fail' } })

    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    // Toast shows error
    expect(screen.getByText(/Save failed: Server error/)).toBeInTheDocument()
  })
})


// --- useDebounce hook ---
describe('useDebounce', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })
  afterEach(() => {
    vi.useRealTimers()
  })

  it('returns initial value immediately', () => {
    const { result } = renderHook(() => useDebounce('initial', 300))
    expect(result.current).toBe('initial')
  })

  it('does not update debounced value before delay', () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 300),
      { initialProps: { value: 'first' } }
    )

    rerender({ value: 'second' })
    vi.advanceTimersByTime(200)
    expect(result.current).toBe('first')
  })

  it('updates debounced value after delay', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 300),
      { initialProps: { value: 'first' } }
    )

    rerender({ value: 'second' })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(300)
    })

    expect(result.current).toBe('second')
  })

  it('resets timer on rapid value changes', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value, 300),
      { initialProps: { value: 'a' } }
    )

    rerender({ value: 'ab' })
    vi.advanceTimersByTime(200)
    rerender({ value: 'abc' })
    vi.advanceTimersByTime(200)
    // Only 200ms after last change, not 300
    expect(result.current).toBe('a')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(100)
    })
    // Now 300ms after last change
    expect(result.current).toBe('abc')
  })

  it('uses default delay of 300ms', async () => {
    const { result, rerender } = renderHook(
      ({ value }) => useDebounce(value),
      { initialProps: { value: 'x' } }
    )

    rerender({ value: 'y' })
    vi.advanceTimersByTime(299)
    expect(result.current).toBe('x')

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1)
    })
    expect(result.current).toBe('y')
  })
})
