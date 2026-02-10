import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'

// --- SwarmHistory ---
import SwarmHistory from '../components/SwarmHistory'

describe('SwarmHistory', () => {
  it('shows loading state initially', () => {
    const fetchHistory = vi.fn(() => new Promise(() => {})) // never resolves
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    // Skeleton loading state shows animated placeholder bones
    const bones = document.querySelectorAll('.animate-pulse')
    expect(bones.length).toBeGreaterThan(0)
  })

  it('shows empty state when no runs', async () => {
    const fetchHistory = vi.fn(() => Promise.resolve({ runs: [] }))
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    await waitFor(() => expect(screen.getByText('No runs yet')).toBeInTheDocument())
  })

  it('renders run table with data', async () => {
    const runs = [
      { id: 1, started_at: '2026-02-06 12:00:00', ended_at: '2026-02-06 12:05:00', status: 'stopped', duration_seconds: 300, tasks_completed: 5 },
      { id: 2, started_at: '2026-02-06 13:00:00', ended_at: null, status: 'running', duration_seconds: null, tasks_completed: 0 },
    ]
    const fetchHistory = vi.fn(() => Promise.resolve({ runs }))
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)

    await waitFor(() => {
      expect(screen.getByRole('table')).toBeInTheDocument()
      expect(screen.getByText('stopped')).toBeInTheDocument()
      expect(screen.getByText('running')).toBeInTheDocument()
      expect(screen.getByText('5m 0s')).toBeInTheDocument()
    })
  })

  it('renders header label', async () => {
    const fetchHistory = vi.fn(() => Promise.resolve({ runs: [] }))
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    await waitFor(() => expect(screen.getByText('Run History')).toBeInTheDocument())
  })

  it('shows error state on fetch failure', async () => {
    const fetchHistory = vi.fn(() => Promise.reject(new Error('Network error')))
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    await waitFor(() => expect(screen.getByText('Network error')).toBeInTheDocument())
  })

  it('calls fetchHistory with projectId', async () => {
    const fetchHistory = vi.fn(() => Promise.resolve({ runs: [] }))
    render(<SwarmHistory projectId={42} fetchHistory={fetchHistory} />)
    await waitFor(() => expect(fetchHistory).toHaveBeenCalledWith(42))
  })

  it('renders table headers', async () => {
    const fetchHistory = vi.fn(() => Promise.resolve({
      runs: [{ id: 1, started_at: '2026-02-06', status: 'stopped', duration_seconds: 60, tasks_completed: 3 }]
    }))
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    await waitFor(() => {
      expect(screen.getByText('Started')).toBeInTheDocument()
      expect(screen.getByText('Duration')).toBeInTheDocument()
      expect(screen.getByText('Status')).toBeInTheDocument()
      expect(screen.getByText('Tasks')).toBeInTheDocument()
    })
  })

  it('formats duration correctly', async () => {
    const fetchHistory = vi.fn(() => Promise.resolve({
      runs: [{ id: 1, started_at: '2026-02-06', status: 'stopped', duration_seconds: 3661, tasks_completed: 0 }]
    }))
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    await waitFor(() => expect(screen.getByText('1h 1m')).toBeInTheDocument())
  })

  it('shows dash for null duration', async () => {
    const fetchHistory = vi.fn(() => Promise.resolve({
      runs: [{ id: 1, started_at: '2026-02-06', status: 'running', duration_seconds: null, tasks_completed: 0 }]
    }))
    render(<SwarmHistory projectId={1} fetchHistory={fetchHistory} />)
    // The — character (em dash)
    await waitFor(() => expect(screen.getAllByText('—').length).toBeGreaterThan(0))
  })
})

// --- TerminalOutput ---
import TerminalOutput, { stripAnsi, parseAnsiLine } from '../components/TerminalOutput'

describe('TerminalOutput', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('shows empty state when no output', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
    })
    expect(screen.getByText('No output yet')).toBeInTheDocument()
  })

  it('renders output lines', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({
      lines: ['[stdout] Hello world', '[stderr] Debug info'],
      next_offset: 2,
    }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.getByText(/Hello world/)).toBeInTheDocument()
    expect(screen.getByText(/Debug info/)).toBeInTheDocument()
  })

  it('has terminal output header', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
    })
    expect(screen.getByText('Terminal Output')).toBeInTheDocument()
  })

  it('has log role for accessibility', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
    })
    expect(screen.getByRole('log')).toBeInTheDocument()
  })

  it('shows line count', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({
      lines: ['line 1', 'line 2', 'line 3'],
      next_offset: 3,
    }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.getByText('3 lines')).toBeInTheDocument()
  })

  it('has clear button', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({
      lines: ['line 1'],
      next_offset: 1,
    }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
    })
    const clearBtn = screen.getByText('Clear')
    expect(clearBtn).toBeInTheDocument()
  })

  it('clears lines when clear button clicked', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({
      lines: ['line 1'],
      next_offset: 1,
    }))
    await act(async () => {
      render(<TerminalOutput projectId={1} fetchOutput={fetchOutput} />)
      await vi.advanceTimersByTimeAsync(100)
    })
    expect(screen.getByText(/line 1/)).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByText('Clear'))
    })
    expect(screen.getByText('No output yet')).toBeInTheDocument()
  })

  it('calls fetchOutput with projectId and offset', async () => {
    const fetchOutput = vi.fn(() => Promise.resolve({ lines: [], next_offset: 0 }))
    await act(async () => {
      render(<TerminalOutput projectId={42} fetchOutput={fetchOutput} />)
    })
    expect(fetchOutput).toHaveBeenCalledWith(42, 0)
  })
})

describe('ANSI parsing', () => {
  it('strips ANSI codes', () => {
    expect(stripAnsi('\x1b[31mRed text\x1b[0m')).toBe('Red text')
  })

  it('strips nested ANSI codes', () => {
    expect(stripAnsi('\x1b[1;32mBold Green\x1b[0m normal')).toBe('Bold Green normal')
  })

  it('returns plain text unchanged', () => {
    expect(stripAnsi('Hello world')).toBe('Hello world')
  })

  it('parseAnsiLine returns segments with classNames', () => {
    const segments = parseAnsiLine('\x1b[31mError\x1b[0m ok')
    expect(segments.length).toBeGreaterThan(1)
    expect(segments[0].text).toBe('Error')
    expect(segments[0].className).toContain('red')
  })

  it('parseAnsiLine handles plain text', () => {
    const segments = parseAnsiLine('plain text')
    expect(segments).toHaveLength(1)
    expect(segments[0].text).toBe('plain text')
  })
})

// --- ProjectSettings ---
import ProjectSettings from '../components/ProjectSettings'

describe('ProjectSettings', () => {
  it('renders form fields', () => {
    render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    expect(screen.getByLabelText('Agent Count')).toBeInTheDocument()
    expect(screen.getByLabelText('Max Phases')).toBeInTheDocument()
    expect(screen.getByLabelText('Custom Prompts')).toBeInTheDocument()
  })

  it('renders with default values', () => {
    render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    expect(screen.getByLabelText('Agent Count')).toHaveValue(4)
    expect(screen.getByLabelText('Max Phases')).toHaveValue(24)
  })

  it('renders with initial config', () => {
    const config = { agent_count: 6, max_phases: 5, custom_prompts: 'Focus on tests' }
    render(<ProjectSettings projectId={1} initialConfig={config} onSave={vi.fn()} />)
    expect(screen.getByLabelText('Agent Count')).toHaveValue(6)
    expect(screen.getByLabelText('Max Phases')).toHaveValue(5)
    expect(screen.getByLabelText('Custom Prompts')).toHaveValue('Focus on tests')
  })

  it('updates agent count on input', () => {
    render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    const input = screen.getByLabelText('Agent Count')
    fireEvent.change(input, { target: { value: '8' } })
    expect(input).toHaveValue(8)
  })

  it('calls onSave with config on submit', async () => {
    const onSave = vi.fn(() => Promise.resolve())
    render(<ProjectSettings projectId={42} onSave={onSave} />)

    await act(async () => {
      fireEvent.click(screen.getByText('Save Settings'))
    })

    expect(onSave).toHaveBeenCalledWith(42, expect.objectContaining({
      agent_count: 4,
      max_phases: 24,
    }))
  })

  it('shows saving state during save', async () => {
    let resolvePromise
    const onSave = vi.fn(() => new Promise((resolve) => { resolvePromise = resolve }))
    render(<ProjectSettings projectId={1} onSave={onSave} />)

    await act(async () => {
      fireEvent.click(screen.getByText('Save Settings'))
    })
    expect(screen.getByText('Saving...')).toBeInTheDocument()

    await act(async () => resolvePromise())
    await waitFor(() => expect(screen.getByText('Saved!')).toBeInTheDocument())
  })

  it('renders header label', () => {
    render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    expect(screen.getByText('Project Settings')).toBeInTheDocument()
  })

  it('has submit button', () => {
    render(<ProjectSettings projectId={1} onSave={vi.fn()} />)
    expect(screen.getByText('Save Settings')).toBeInTheDocument()
  })
})
