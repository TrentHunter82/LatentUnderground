import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'

// Mock react-markdown and remark/rehype plugins before any imports
vi.mock('react-markdown', () => ({
  default: ({ children }) => <div data-testid="markdown-preview">{children}</div>,
}))
vi.mock('remark-gfm', () => ({ default: {} }))
vi.mock('rehype-highlight', () => ({ default: {} }))

// Mock API module
vi.mock('../lib/api', () => ({
  getFile: vi.fn(),
  putFile: vi.fn(),
}))

import { getFile, putFile } from '../lib/api'
import { ToastProvider } from '../components/Toast'
import FileEditor from '../components/FileEditor'

const SAMPLE_CONTENT = '# Tasks\n- [x] Done'

function renderEditor(props = {}) {
  return render(
    <ToastProvider>
      <FileEditor projectId={1} {...props} />
    </ToastProvider>
  )
}

describe('FileEditor', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getFile.mockResolvedValue({ content: SAMPLE_CONTENT })
    putFile.mockResolvedValue({ ok: true })
  })

  // -------------------------------------------------------
  // 1. Renders file tabs (Tasks, Lessons, Plans)
  // -------------------------------------------------------
  it('renders all three file tabs', async () => {
    await act(async () => { renderEditor() })

    expect(screen.getByText('Tasks')).toBeInTheDocument()
    expect(screen.getByText('Lessons')).toBeInTheDocument()
    expect(screen.getByText('Plans')).toBeInTheDocument()
  })

  // -------------------------------------------------------
  // 2. Loads file content on mount (calls getFile correctly)
  // -------------------------------------------------------
  it('loads file content on mount with correct arguments', async () => {
    await act(async () => { renderEditor({ projectId: 42 }) })

    expect(getFile).toHaveBeenCalledWith('tasks/TASKS.md', 42)
  }, 15000)

  // -------------------------------------------------------
  // 3. Shows markdown preview of file content
  // -------------------------------------------------------
  it('shows markdown preview of loaded content', async () => {
    await act(async () => { renderEditor() })

    const preview = screen.getByTestId('markdown-preview')
    expect(preview).toBeInTheDocument()
    expect(preview.textContent).toBe(SAMPLE_CONTENT)
  })

  // -------------------------------------------------------
  // 4. Shows '*Empty file*' when content is empty
  // -------------------------------------------------------
  it('shows empty file placeholder when content is empty', async () => {
    getFile.mockResolvedValue({ content: '' })

    await act(async () => { renderEditor() })

    const preview = screen.getByTestId('markdown-preview')
    expect(preview.textContent).toBe('*Empty file*')
  })

  // -------------------------------------------------------
  // 5. Switching tabs loads a different file
  // -------------------------------------------------------
  it('loads different file when switching tabs', async () => {
    await act(async () => { renderEditor() })

    // Initial load is tasks/TASKS.md
    expect(getFile).toHaveBeenCalledWith('tasks/TASKS.md', 1)

    // Click the Lessons tab
    await act(async () => {
      fireEvent.click(screen.getByText('Lessons'))
    })

    await waitFor(() => {
      expect(getFile).toHaveBeenCalledWith('tasks/lessons.md', 1)
    })

    // Click the Plans tab
    await act(async () => {
      fireEvent.click(screen.getByText('Plans'))
    })

    await waitFor(() => {
      expect(getFile).toHaveBeenCalledWith('tasks/todo.md', 1)
    })
  })

  // -------------------------------------------------------
  // 6. Edit button shows textarea with content
  // -------------------------------------------------------
  it('switches to edit mode with textarea when Edit is clicked', async () => {
    await act(async () => { renderEditor() })

    // No textarea initially
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()

    // Click Edit
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    const textarea = screen.getByRole('textbox')
    expect(textarea).toBeInTheDocument()
    expect(textarea.value).toBe(SAMPLE_CONTENT)
  })

  // -------------------------------------------------------
  // 7. Cancel reverts changes and exits edit mode
  // -------------------------------------------------------
  it('reverts changes and exits edit mode on Cancel', async () => {
    await act(async () => { renderEditor() })

    // Enter edit mode
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    const textarea = screen.getByRole('textbox')

    // Make changes
    await act(async () => {
      fireEvent.change(textarea, { target: { value: 'Modified content' } })
    })
    expect(textarea.value).toBe('Modified content')

    // Click Cancel
    await act(async () => {
      fireEvent.click(screen.getByText('Cancel'))
    })

    // Should be back in preview mode with original content
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    const preview = screen.getByTestId('markdown-preview')
    expect(preview.textContent).toBe(SAMPLE_CONTENT)
  })

  // -------------------------------------------------------
  // 8. Save button disabled when content unchanged
  // -------------------------------------------------------
  it('disables Save button when content has not changed', async () => {
    await act(async () => { renderEditor() })

    // Enter edit mode (content matches original)
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    const saveButton = screen.getByText('Save')
    expect(saveButton).toBeDisabled()
  })

  // -------------------------------------------------------
  // 8b. Save button enabled when content changed
  // -------------------------------------------------------
  it('enables Save button when content has changed', async () => {
    await act(async () => { renderEditor() })

    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'new stuff' } })
    })

    const saveButton = screen.getByText('Save')
    expect(saveButton).not.toBeDisabled()
  })

  // -------------------------------------------------------
  // 9. Save calls putFile with correct arguments
  // -------------------------------------------------------
  it('calls putFile with correct args on Save', async () => {
    await act(async () => { renderEditor({ projectId: 7 }) })

    // Enter edit mode
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    // Modify content
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'Updated content' } })
    })

    // Save
    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    expect(putFile).toHaveBeenCalledWith('tasks/TASKS.md', 'Updated content', 7)
  })

  // -------------------------------------------------------
  // 10. Shows "Saving..." during save
  // -------------------------------------------------------
  it('shows "Saving..." text while save is in progress', async () => {
    // Make putFile hang until we resolve it
    let resolveSave
    putFile.mockImplementation(() => new Promise((resolve) => { resolveSave = resolve }))

    await act(async () => { renderEditor() })

    // Enter edit mode and modify
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'changed' } })
    })

    // Click save (don't await the full resolution)
    act(() => {
      fireEvent.click(screen.getByText('Save'))
    })

    // Should show Saving... while promise is pending
    expect(screen.getByText('Saving...')).toBeInTheDocument()

    // Resolve the save
    await act(async () => {
      resolveSave({ ok: true })
    })

    // After save completes, should no longer show Saving...
    expect(screen.queryByText('Saving...')).not.toBeInTheDocument()
  })

  // -------------------------------------------------------
  // 11. Error displayed on load failure
  // -------------------------------------------------------
  it('displays error message when file load fails', async () => {
    getFile.mockRejectedValue(new Error('Network error'))

    await act(async () => { renderEditor() })

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })
  })

  // -------------------------------------------------------
  // 11b. Error displayed on save failure
  // -------------------------------------------------------
  it('displays error message when save fails', async () => {
    putFile.mockRejectedValue(new Error('Permission denied'))

    await act(async () => { renderEditor() })

    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'new content' } })
    })
    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    await waitFor(() => {
      expect(screen.getByText('Permission denied')).toBeInTheDocument()
    })
  })

  // -------------------------------------------------------
  // 12. Auto-reload on file_changed wsEvent (not editing)
  // -------------------------------------------------------
  it('auto-reloads when wsEvents has file_changed for active file', async () => {
    await act(async () => { renderEditor() })

    // Initial load
    expect(getFile).toHaveBeenCalledTimes(1)

    // Simulate a file_changed WebSocket event
    getFile.mockResolvedValue({ content: '# Updated Tasks' })

    const { rerender } = render(
      <ToastProvider>
        <FileEditor
          projectId={1}
          wsEvents={{ type: 'file_changed', file: 'tasks/TASKS.md' }}
        />
      </ToastProvider>
    )

    await waitFor(() => {
      // getFile called again due to the wsEvent
      expect(getFile).toHaveBeenCalledTimes(3) // initial + rerender mount + ws event
    })
  })

  // -------------------------------------------------------
  // 13. Does NOT auto-reload when editing
  // -------------------------------------------------------
  it('does NOT auto-reload on file_changed event when in edit mode', async () => {
    const { rerender } = await act(async () => renderEditor())

    const initialCallCount = getFile.mock.calls.length

    // Enter edit mode
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    // Modify to have unsaved changes
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'my edits' } })
    })

    // Simulate file_changed event while editing
    await act(async () => {
      rerender(
        <ToastProvider>
          <FileEditor
            projectId={1}
            wsEvents={{ type: 'file_changed', file: 'tasks/TASKS.md' }}
          />
        </ToastProvider>
      )
    })

    // getFile should NOT have been called again
    expect(getFile).toHaveBeenCalledTimes(initialCallCount)

    // Edits should be preserved
    expect(screen.getByRole('textbox').value).toBe('my edits')
  })

  // -------------------------------------------------------
  // 14. Shows "Updated" timestamp after successful load
  // -------------------------------------------------------
  it('shows "Updated" timestamp after successful file load', async () => {
    await act(async () => { renderEditor() })

    await waitFor(() => {
      expect(screen.getByText(/Updated/)).toBeInTheDocument()
    })
  })

  // -------------------------------------------------------
  // 15. Keyboard shortcut: Ctrl+S saves when editing
  // -------------------------------------------------------
  it('saves on Ctrl+S keyboard shortcut when editing', async () => {
    await act(async () => { renderEditor() })

    // Enter edit mode
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    // Modify content
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'keyboard save' } })
    })

    // Press Ctrl+S
    await act(async () => {
      fireEvent.keyDown(window, { key: 's', ctrlKey: true })
    })

    expect(putFile).toHaveBeenCalledWith('tasks/TASKS.md', 'keyboard save', 1)
  })

  // -------------------------------------------------------
  // 16. Keyboard shortcut: Escape cancels editing
  // -------------------------------------------------------
  it('cancels editing on Escape key', async () => {
    await act(async () => { renderEditor() })

    // Enter edit mode
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    // Modify content
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'will be cancelled' } })
    })

    // Press Escape
    await act(async () => {
      fireEvent.keyDown(window, { key: 'Escape' })
    })

    // Should exit edit mode and revert content
    expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
    const preview = screen.getByTestId('markdown-preview')
    expect(preview.textContent).toBe(SAMPLE_CONTENT)
  })

  // -------------------------------------------------------
  // 17. Save exits edit mode on success
  // -------------------------------------------------------
  it('exits edit mode after successful save', async () => {
    await act(async () => { renderEditor() })

    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'saved content' } })
    })
    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    await waitFor(() => {
      // Should show preview mode, not textarea
      expect(screen.queryByRole('textbox')).not.toBeInTheDocument()
      const preview = screen.getByTestId('markdown-preview')
      expect(preview.textContent).toBe('saved content')
    })
  })

  // -------------------------------------------------------
  // 18. Stays in edit mode on save failure
  // -------------------------------------------------------
  it('stays in edit mode when save fails', async () => {
    putFile.mockRejectedValue(new Error('Save failed'))

    await act(async () => { renderEditor() })

    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })
    await act(async () => {
      fireEvent.change(screen.getByRole('textbox'), { target: { value: 'unsaved content' } })
    })
    await act(async () => {
      fireEvent.click(screen.getByText('Save'))
    })

    await waitFor(() => {
      // Should still be in edit mode with our changes
      const textarea = screen.getByRole('textbox')
      expect(textarea).toBeInTheDocument()
      expect(textarea.value).toBe('unsaved content')
    })
  })

  // -------------------------------------------------------
  // 19. Edit button is present in preview mode
  // -------------------------------------------------------
  it('shows Edit button in preview mode', async () => {
    await act(async () => { renderEditor() })

    expect(screen.getByText('Edit')).toBeInTheDocument()
  })

  // -------------------------------------------------------
  // 20. Edit mode shows Save and Cancel but not Edit
  // -------------------------------------------------------
  it('shows Save and Cancel buttons in edit mode, hides Edit button', async () => {
    await act(async () => { renderEditor() })

    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    expect(screen.getByText('Save')).toBeInTheDocument()
    expect(screen.getByText('Cancel')).toBeInTheDocument()
    expect(screen.queryByText('Edit')).not.toBeInTheDocument()
  })

  // -------------------------------------------------------
  // 21. Ignores wsEvents that are not file_changed type
  // -------------------------------------------------------
  it('ignores wsEvents that are not file_changed type', async () => {
    await act(async () => { renderEditor() })

    const callsAfterMount = getFile.mock.calls.length

    const { rerender } = render(
      <ToastProvider>
        <FileEditor
          projectId={1}
          wsEvents={{ type: 'heartbeat', agent: 'Claude-1' }}
        />
      </ToastProvider>
    )

    // Should not trigger another getFile call for non-file_changed events
    // (only the new mount call, not an additional reload)
    await waitFor(() => {
      // The rerender creates a new mount (1 call), but no extra ws-triggered reload
      const totalCalls = getFile.mock.calls.length
      // Each mount = 1 call; we have original mount + rerender mount
      expect(totalCalls).toBeLessThanOrEqual(callsAfterMount + 1)
    })
  })

  // -------------------------------------------------------
  // 22. Ignores wsEvents for files other than active file
  // -------------------------------------------------------
  it('ignores file_changed events for a different file', async () => {
    const { rerender } = await act(async () => renderEditor())

    const callsAfterMount = getFile.mock.calls.length

    await act(async () => {
      rerender(
        <ToastProvider>
          <FileEditor
            projectId={1}
            wsEvents={{ type: 'file_changed', file: 'some/other/file.md' }}
          />
        </ToastProvider>
      )
    })

    // No additional getFile calls because the changed file doesn't match active
    expect(getFile).toHaveBeenCalledTimes(callsAfterMount)
  })
})
