import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, act } from '@testing-library/react'

// --- LogViewer Performance ---
import LogViewer from '../components/LogViewer'

// Mock api.getLogs
vi.mock('../lib/api', () => ({
  getLogs: vi.fn(),
}))

import { getLogs } from '../lib/api'

describe('LogViewer Performance', () => {
  it('renders 1000 log lines without crashing', async () => {
    const lines = Array.from({ length: 1000 }, (_, i) => `Log line ${i}`)
    getLogs.mockResolvedValue({
      logs: [{ agent: 'Claude-1', lines }],
    })

    const start = performance.now()
    await act(async () => {
      render(<LogViewer projectId={1} />)
    })
    const elapsed = performance.now() - start

    // Should render all 1000 lines
    expect(screen.getByText('Log line 0')).toBeInTheDocument()
    expect(screen.getByText('Log line 999')).toBeInTheDocument()
    // Should render in reasonable time (< 2000ms)
    expect(elapsed).toBeLessThan(2000)
  })

  it('truncates buffer at 1000 lines via WebSocket append', async () => {
    // Start with 995 lines
    const initial = Array.from({ length: 995 }, (_, i) => `Initial ${i}`)
    getLogs.mockResolvedValue({
      logs: [{ agent: 'Claude-1', lines: initial }],
    })

    const { rerender } = await act(async () => {
      return render(<LogViewer projectId={1} />)
    })

    // Append 10 more via WebSocket event
    const wsEvent = {
      type: 'log',
      agent: 'Claude-2',
      lines: Array.from({ length: 10 }, (_, i) => `WS line ${i}`),
    }

    await act(async () => {
      rerender(<LogViewer projectId={1} wsEvents={wsEvent} />)
    })

    // Buffer should be capped at 1000
    // The last WS line should be present
    expect(screen.getByText('WS line 9')).toBeInTheDocument()
    // Early initial lines may be trimmed (995 + 10 = 1005, trimmed to 1000)
    // So Initial 0 through Initial 4 should be gone
    expect(screen.queryByText('Initial 0')).not.toBeInTheDocument()
  })

  it('filters 1000 lines efficiently', async () => {
    const lines = Array.from({ length: 500 }, (_, i) => `Line ${i}`)
    getLogs.mockResolvedValue({
      logs: [
        { agent: 'Claude-1', lines },
        { agent: 'Claude-2', lines },
      ],
    })

    await act(async () => {
      render(<LogViewer projectId={1} />)
    })

    // All agent filter buttons should be present
    expect(screen.getAllByText('All').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('Claude-1')).toBeInTheDocument()
    expect(screen.getByText('Claude-2')).toBeInTheDocument()
  })
})

// --- TerminalOutput Performance ---
import TerminalOutput from '../components/TerminalOutput'

describe('TerminalOutput Performance', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('renders 1000 terminal lines without crashing', async () => {
    const lines = Array.from({ length: 1000 }, (_, i) => `[stdout] Output line ${i}`)
    const fetchOutput = vi.fn(() => Promise.resolve({ lines, next_offset: 1000 }))

    const start = performance.now()
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
      await vi.advanceTimersByTimeAsync(100)
    })
    const elapsed = performance.now() - start

    expect(screen.getByText(/Output line 0/)).toBeInTheDocument()
    expect(screen.getByText(/Output line 999/)).toBeInTheDocument()
    expect(screen.getByText('1000 lines')).toBeInTheDocument()
    // Should render in reasonable time
    expect(elapsed).toBeLessThan(2000)
  })

  it('caps TerminalOutput at 1000 lines', async () => {
    const lines = Array.from({ length: 1100 }, (_, i) => `[stdout] Line ${i}`)
    const fetchOutput = vi.fn(() => Promise.resolve({ lines, next_offset: 1100 }))

    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
      await vi.advanceTimersByTimeAsync(100)
    })

    // Should show 1000 (the cap), not 1100
    expect(screen.getByText('1000 lines')).toBeInTheDocument()
    // The last line should be present (1099)
    expect(screen.getByText(/Line 1099/)).toBeInTheDocument()
    // The first line should be trimmed (0 through 99)
    expect(screen.queryByText(/^.*Line 0$/)).not.toBeInTheDocument()
  })
})
