import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { createApiMock, createSwarmQueryMock, createMutationsMock } from './test-utils'

// Mock react-markdown and remark/rehype plugins before any imports
vi.mock('react-markdown', () => ({
  default: ({ children }) => <div data-testid="markdown-preview">{children}</div>,
}))
vi.mock('remark-gfm', () => ({ default: {} }))
vi.mock('rehype-highlight', () => ({ default: {} }))

// Mock API module
vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getFile: vi.fn(),
  putFile: vi.fn(),
  sendSwarmInput: vi.fn(),
  getProjectQuota: vi.fn(() => Promise.resolve({})),
  getSystemInfo: vi.fn(() => Promise.resolve({})),
  getSystemHealth: vi.fn(() => Promise.resolve({ status: 'ok' })),
  getMetrics: vi.fn(() => Promise.resolve('')),
  getHealthTrends: vi.fn(() => Promise.resolve({})),
  getProjectHealth: vi.fn(() => Promise.resolve({ crash_rate: 0, trend: 'stable', classification: 'healthy', total_runs: 0 })),
  getRunCheckpoints: vi.fn(() => Promise.resolve([])),
}))

vi.mock('../hooks/useSwarmQuery', () => createSwarmQueryMock())
vi.mock('../hooks/useMutations', () => createMutationsMock())

import { getFile, putFile } from '../lib/api'
import { ToastProvider } from '../components/Toast'
import FileEditor from '../components/FileEditor'
import TerminalOutput from '../components/TerminalOutput'
import ProjectSettings from '../components/ProjectSettings'

// ============================================================
// FileEditor - 404 Handling
// ============================================================

const SAMPLE_CONTENT = '# Tasks\n- [x] Done'

function renderEditor(props = {}) {
  return render(
    <ToastProvider>
      <FileEditor projectId={1} {...props} />
    </ToastProvider>
  )
}

describe('FileEditor - 404 handling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    putFile.mockResolvedValue({ ok: true })
  })

  it('does not show error when file returns 404', async () => {
    getFile.mockRejectedValue(new Error('Request failed: 404 Not Found'))

    await act(async () => { renderEditor() })

    // Should NOT display the error text anywhere
    expect(screen.queryByText(/404/)).not.toBeInTheDocument()
    // Should show the new placeholder in the markdown preview
    const preview = screen.getByTestId('markdown-preview')
    expect(preview.textContent).toContain('File not created yet')
  })

  it('shows placeholder with full expected text on 404', async () => {
    getFile.mockRejectedValue(new Error('404'))

    await act(async () => { renderEditor() })

    const preview = screen.getByTestId('markdown-preview')
    expect(preview.textContent).toContain('it will appear once the swarm generates it')
  })

  it('sets content to empty string on 404 so placeholder is shown', async () => {
    getFile.mockRejectedValue(new Error('Not found: 404'))

    await act(async () => { renderEditor() })

    // Enter edit mode to check the actual content value
    await act(async () => {
      fireEvent.click(screen.getByText('Edit'))
    })

    const textarea = screen.getByRole('textbox')
    expect(textarea.value).toBe('')
  })

  it('does not show "Updated" timestamp on 404 (lastModified is null)', async () => {
    getFile.mockRejectedValue(new Error('404 Not Found'))

    await act(async () => { renderEditor() })

    expect(screen.queryByText(/Updated/)).not.toBeInTheDocument()
  })

  it('still shows error for non-404 failures', async () => {
    getFile.mockRejectedValue(new Error('Network error'))

    await act(async () => { renderEditor() })

    await waitFor(() => {
      expect(screen.getByText('Network error')).toBeInTheDocument()
    })
  })

  it('still shows error for 500 server error', async () => {
    getFile.mockRejectedValue(new Error('Internal Server Error'))

    await act(async () => { renderEditor() })

    await waitFor(() => {
      expect(screen.getByText('Internal Server Error')).toBeInTheDocument()
    })
  })

  it('recovers from 404 when file becomes available', async () => {
    // First load: 404
    getFile.mockRejectedValue(new Error('404 Not Found'))
    const { rerender } = await act(async () => renderEditor())

    expect(screen.queryByText(/404/)).not.toBeInTheDocument()
    const preview = screen.getByTestId('markdown-preview')
    expect(preview.textContent).toContain('File not created yet')

    // Now file becomes available via tab switch
    getFile.mockResolvedValue({ content: '# Real content' })

    await act(async () => {
      fireEvent.click(screen.getByText('Lessons'))
    })

    await waitFor(() => {
      const updatedPreview = screen.getByTestId('markdown-preview')
      expect(updatedPreview.textContent).toBe('# Real content')
    })
  })

  it('does not show toast notification for 404 errors', async () => {
    getFile.mockRejectedValue(new Error('Request failed: 404'))

    await act(async () => { renderEditor() })

    // Toast messages for load failures contain "Failed to load file"
    // On 404, no toast should appear
    expect(screen.queryByText(/Failed to load file/)).not.toBeInTheDocument()
  })

  it('shows toast notification for non-404 errors', async () => {
    getFile.mockRejectedValue(new Error('Permission denied'))

    await act(async () => { renderEditor() })

    await waitFor(() => {
      // The toast renders "Failed to load file: Permission denied"
      expect(screen.getByText(/Failed to load file/)).toBeInTheDocument()
    })
  })
})

// ============================================================
// TerminalOutput - Adaptive Polling
// ============================================================

describe('TerminalOutput - adaptive polling', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('performs initial poll immediately on mount', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // poll() is called immediately, not after a delay
    expect(fetchOutput).toHaveBeenCalledTimes(1)
    expect(fetchOutput).toHaveBeenCalledWith(1, 0, null, expect.objectContaining({}))
  })

  it('polls with 1500ms delay when receiving data', async () => {
    let callCount = 0
    const fetchOutput = vi.fn(() => {
      callCount++
      return Promise.resolve({
        lines: [`line ${callCount}`],
        next_offset: callCount,
      })
    })

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // Initial poll completed
    expect(fetchOutput).toHaveBeenCalledTimes(1)

    // Advance 1500ms — the active polling interval
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })

    expect(fetchOutput).toHaveBeenCalledTimes(2)

    // Advance another 1500ms — still active since data was returned
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })

    expect(fetchOutput).toHaveBeenCalledTimes(3)
  })

  it('increases poll delay to 3000ms after 3 idle polls', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // Initial poll (idle #1, idleCount becomes 1)
    expect(fetchOutput).toHaveBeenCalledTimes(1)

    // Poll #2: advance 1500ms (idleCount < 3, so 1500ms delay)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(2) // idle #2

    // Poll #3: advance 1500ms (idleCount still < 3, so 1500ms delay)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(3) // idle #3, idleCount becomes 3

    // Now idleCount >= 3, delay should be 3000ms
    // Advancing 1500ms should NOT trigger another poll
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(3) // no new poll yet

    // Advance remaining 1500ms (total 3000ms since last poll)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(4) // now poll fires
  })

  it('increases poll delay to 5000ms after 10 idle polls', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // Run through first 3 idle polls at 1500ms each
    // Poll 1 already happened on mount (idleCount=1)
    // Polls 2-3: 1500ms intervals (idleCount < 3)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500) // poll #2, idle=2
    })
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500) // poll #3, idle=3
    })

    // Polls 4-10 at 3000ms (idleCount 3-9)
    for (let i = 0; i < 7; i++) {
      await act(async () => {
        await vi.advanceTimersByTimeAsync(3000)
      })
    }

    // idleCount is now 10 after poll #10
    expect(fetchOutput).toHaveBeenCalledTimes(10)

    // Now delay should be 5000ms. Advancing 3000ms should NOT trigger poll.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(10) // no new poll yet

    // Advance remaining 2000ms (total 5000ms)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(11) // poll fires at 5000ms
  })

  it('stops polling when component unmounts', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))

    const { unmount } = await act(async () => {
      return render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    expect(fetchOutput).toHaveBeenCalledTimes(1)

    // Unmount the component
    unmount()

    // Advance time — no more polls should fire
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000)
    })

    expect(fetchOutput).toHaveBeenCalledTimes(1) // no additional calls
  })

  it('resets idle count when new data arrives after idle period', async () => {
    let callIndex = 0
    const responses = [
      { lines: [], next_offset: 0 },   // idle #1
      { lines: [], next_offset: 0 },   // idle #2
      { lines: [], next_offset: 0 },   // idle #3 → idleCount=3, next delay=3000
      { lines: ['new data'], next_offset: 1 }, // data! resets idleCount=0
      // After reset, delay should be 1500ms again
    ]
    const fetchOutput = vi.fn(() => {
      const response = responses[callIndex] || { lines: [], next_offset: 0 }
      callIndex++
      return Promise.resolve(response)
    })

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // Poll #1 (mount): idle=1
    expect(fetchOutput).toHaveBeenCalledTimes(1)

    // Poll #2: 1500ms, idle=2
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(2)

    // Poll #3: 1500ms, idle=3
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(3)

    // Poll #4: 3000ms (idleCount was 3), but returns data → resets idleCount to 0
    await act(async () => {
      await vi.advanceTimersByTimeAsync(3000)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(4)

    // After reset, delay should be 1500ms again (idleCount < 3)
    // Advancing only 1500ms should trigger poll
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(5)
  })

  it('uses setTimeout not setInterval for polling', async () => {
    const setTimeoutSpy = vi.spyOn(global, 'setTimeout')
    const setIntervalSpy = vi.spyOn(global, 'setInterval')

    const initialSetTimeoutCalls = setTimeoutSpy.mock.calls.length
    const initialSetIntervalCalls = setIntervalSpy.mock.calls.length

    const fetchOutput = vi.fn(() => Promise.resolve({ lines: ['data'], next_offset: 1 }))

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // After mount + first poll, setTimeout should have been called at least once
    // for scheduling the next poll
    const newSetTimeoutCalls = setTimeoutSpy.mock.calls.length - initialSetTimeoutCalls
    const newSetIntervalCalls = setIntervalSpy.mock.calls.length - initialSetIntervalCalls

    expect(newSetTimeoutCalls).toBeGreaterThan(0)
    expect(newSetIntervalCalls).toBe(0)

    setTimeoutSpy.mockRestore()
    setIntervalSpy.mockRestore()
  })

  it('handles fetch errors gracefully and increments idle count', async () => {
    let callIndex = 0
    const fetchOutput = vi.fn(() => {
      callIndex++
      if (callIndex <= 3) {
        return Promise.reject(new Error('Network error'))
      }
      return Promise.resolve({ lines: [], next_offset: 0 })
    })

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // Poll #1: error (idleCount incremented to 1)
    expect(fetchOutput).toHaveBeenCalledTimes(1)

    // Poll #2: 1500ms (idleCount < 3), error again
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(2)

    // Poll #3: 1500ms (idleCount still < 3), error again → idleCount=3
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(3)

    // Poll #4 should use 3000ms delay (idleCount >= 3)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(3) // not yet

    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(fetchOutput).toHaveBeenCalledTimes(4)
  })

  it('does not poll when projectId is null', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))

    await act(async () => {
      render(<TerminalOutput projectId={null} fetchOutput={fetchOutput} isRunning={true} />)
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000)
    })

    expect(fetchOutput).not.toHaveBeenCalled()
  })

  it('does not poll when fetchOutput is null', async () => {
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={null} isRunning={true} />)
    })

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10000)
    })

    // Should not throw and should render fine
    // With isRunning=true, shows "Waiting for agent output..." instead of "No output yet"
    expect(screen.getByText('Waiting for agent output...')).toBeInTheDocument()
  })

  it('shows error banner after 3 consecutive poll failures', async () => {
    const fetchOutput = vi.fn(() => Promise.reject(new Error('Network error')))

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // Poll #1: error (errorCount=1)
    expect(fetchOutput).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    // Poll #2: error (errorCount=2)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()

    // Poll #3: error (errorCount=3) → banner appears
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500)
    })
    expect(screen.getByRole('alert')).toBeInTheDocument()
    expect(screen.getByText(/Connection lost/)).toBeInTheDocument()
  })

  it('hides error banner when poll recovers', async () => {
    let callIndex = 0
    const fetchOutput = vi.fn(() => {
      callIndex++
      if (callIndex <= 3) return Promise.reject(new Error('fail'))
      return Promise.resolve({ lines: ['recovered'], next_offset: 1 })
    })

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} isRunning={true} />)
    })

    // 3 failures → banner appears (poll #1 on mount, #2 at 1500ms, #3 at 1500ms)
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    await act(async () => { await vi.advanceTimersByTimeAsync(1500) })
    expect(screen.getByRole('alert')).toBeInTheDocument()

    // Poll #4: idleCount=3, so delay is 3000ms. This poll succeeds → banner hides
    await act(async () => { await vi.advanceTimersByTimeAsync(3000) })
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

// ============================================================
// FileEditor - Keyboard Navigation
// ============================================================

describe('FileEditor - keyboard navigation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    getFile.mockResolvedValue({ content: '# Tasks' })
    putFile.mockResolvedValue({ ok: true })
  })

  it('has tablist role on tab container', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    expect(screen.getByRole('tablist')).toBeInTheDocument()
  })

  it('active tab has tabIndex 0, others have -1', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    const tabs = screen.getAllByRole('tab')
    const activeTab = tabs.find(t => t.getAttribute('aria-selected') === 'true')
    const inactiveTabs = tabs.filter(t => t.getAttribute('aria-selected') === 'false')

    expect(activeTab).toHaveAttribute('tabindex', '0')
    inactiveTabs.forEach(t => expect(t).toHaveAttribute('tabindex', '-1'))
  })

  it('tabs have aria-controls attribute', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    const tabs = screen.getAllByRole('tab')
    tabs.forEach(t => expect(t).toHaveAttribute('aria-controls', 'file-editor-panel'))
  })

  it('has tabpanel role on content area', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    expect(screen.getByRole('tabpanel')).toBeInTheDocument()
  })

  it('ArrowRight moves to next tab', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    const tabs = screen.getAllByRole('tab')
    // First tab (Tasks) is active
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')

    // Press ArrowRight on active tab
    await act(async () => {
      fireEvent.keyDown(tabs[0], { key: 'ArrowRight' })
    })

    // Second tab (Lessons) should now be active
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Lessons/i })).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('ArrowLeft wraps from first to last tab', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    const tabs = screen.getAllByRole('tab')
    expect(tabs[0]).toHaveAttribute('aria-selected', 'true')

    // Press ArrowLeft on first tab
    await act(async () => {
      fireEvent.keyDown(tabs[0], { key: 'ArrowLeft' })
    })

    // Last tab (Plans) should now be active
    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Plans/i })).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('Home key moves to first tab', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    // Switch to Lessons tab first
    await act(async () => {
      fireEvent.click(screen.getByText('Lessons'))
    })

    const lessonsTab = screen.getByRole('tab', { name: /Lessons/i })
    expect(lessonsTab).toHaveAttribute('aria-selected', 'true')

    // Press Home
    await act(async () => {
      fireEvent.keyDown(lessonsTab, { key: 'Home' })
    })

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Tasks/i })).toHaveAttribute('aria-selected', 'true')
    })
  })

  it('End key moves to last tab', async () => {
    await act(async () => {
      render(<ToastProvider><FileEditor projectId={1} /></ToastProvider>)
    })

    const firstTab = screen.getAllByRole('tab')[0]

    // Press End
    await act(async () => {
      fireEvent.keyDown(firstTab, { key: 'End' })
    })

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /Plans/i })).toHaveAttribute('aria-selected', 'true')
    })
  })
})

// ============================================================
// ProjectSettings - Input Clamping
// ============================================================

describe('ProjectSettings - input clamping', () => {
  it('clamps agent count to maximum of 10', async () => {
    await act(async () => {
      render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    })

    const input = screen.getByLabelText(/Agent Count/i)
    await act(async () => {
      fireEvent.change(input, { target: { value: '50' } })
    })

    expect(input.value).toBe('10')
  })

  it('clamps agent count to minimum of 1', async () => {
    await act(async () => {
      render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    })

    const input = screen.getByLabelText(/Agent Count/i)
    await act(async () => {
      fireEvent.change(input, { target: { value: '0' } })
    })

    expect(input.value).toBe('1')
  })

  it('clamps max phases to maximum of 24', async () => {
    await act(async () => {
      render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    })

    const input = screen.getByLabelText(/Max Phases/i)
    await act(async () => {
      fireEvent.change(input, { target: { value: '100' } })
    })

    expect(input.value).toBe('24')
  })

  it('clamps max phases to minimum of 1', async () => {
    await act(async () => {
      render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    })

    const input = screen.getByLabelText(/Max Phases/i)
    await act(async () => {
      fireEvent.change(input, { target: { value: '-5' } })
    })

    expect(input.value).toBe('1')
  })

  it('accepts valid values within range', async () => {
    await act(async () => {
      render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    })

    const agentInput = screen.getByLabelText(/Agent Count/i)
    await act(async () => {
      fireEvent.change(agentInput, { target: { value: '7' } })
    })
    expect(agentInput.value).toBe('7')

    const phaseInput = screen.getByLabelText(/Max Phases/i)
    await act(async () => {
      fireEvent.change(phaseInput, { target: { value: '12' } })
    })
    expect(phaseInput.value).toBe('12')
  })

  it('handles empty input by defaulting to 1', async () => {
    await act(async () => {
      render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    })

    const input = screen.getByLabelText(/Agent Count/i)
    await act(async () => {
      fireEvent.change(input, { target: { value: '' } })
    })

    expect(input.value).toBe('1')
  })
})
