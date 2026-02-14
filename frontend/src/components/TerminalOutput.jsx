import { useState, useEffect, useRef, useCallback, useMemo, startTransition } from 'react'
import { useVirtualizer } from '@tanstack/react-virtual'
import { createAbortable } from '../lib/api'
import { useSwarmAgents } from '../hooks/useSwarmQuery'
import { useStopSwarmAgent, useSendSwarmInput } from '../hooks/useMutations'
import { AGENT_NEON_COLORS, AGENT_ROLES } from '../lib/constants'
import DirectivePanel from './DirectivePanel'

const MAX_LINES = 10000

// Error detection pattern (case-insensitive)
const ERROR_PATTERN = /\b(error|Error|ERROR|FAILED|Failed|traceback|Traceback|exception|Exception|EXCEPTION|panic|PANIC)\b/

const ANSI_COLORS = {
  '30': 'text-zinc-900', '31': 'text-signal-red', '32': 'text-crt-green',
  '33': 'text-crt-amber', '34': 'text-crt-cyan', '35': 'text-crt-magenta',
  '36': 'text-crt-cyan', '37': 'text-zinc-200',
  '90': 'text-zinc-500', '91': 'text-signal-red', '92': 'text-crt-green',
  '93': 'text-crt-amber', '94': 'text-crt-cyan', '95': 'text-crt-magenta',
  '96': 'text-crt-cyan', '97': 'text-white',
}

function stripAnsi(text) {
  return text.replace(/\x1b\[[0-9;]*m/g, '')
}

function parseAnsiLine(text) {
  const parts = []
  const regex = /\x1b\[([0-9;]*)m/g
  let lastIndex = 0
  let currentClass = 'text-zinc-300'
  let match

  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ text: text.slice(lastIndex, match.index), className: currentClass })
    }
    const code = match[1]
    if (code === '0' || code === '') {
      currentClass = 'text-zinc-300'
    } else {
      currentClass = ANSI_COLORS[code] || currentClass
    }
    lastIndex = regex.lastIndex
  }
  if (lastIndex < text.length) {
    parts.push({ text: text.slice(lastIndex), className: currentClass })
  }
  return parts.length ? parts : [{ text, className: 'text-zinc-300' }]
}

export default function TerminalOutput({ projectId, fetchOutput, isRunning }) {
  const [lines, setLines] = useState([])
  const [autoScroll, setAutoScroll] = useState(true)
  const [inputText, setInputText] = useState('')
  const [inputError, setInputError] = useState(null)
  const [pollError, setPollError] = useState(false)
  const [agentFilter, setAgentFilter] = useState(null) // null = "All"
  const [stoppingAgent, setStoppingAgent] = useState(null)
  const [directiveAgent, setDirectiveAgent] = useState(null) // agent name or null
  const containerRef = useRef(null)
  const offsetRef = useRef(0)
  const intervalRef = useRef(null)
  const inputRef = useRef(null)
  const errorTimerRef = useRef(null)
  const autoScrollRef = useRef(true)

  // TanStack Query: poll agent list with adaptive interval
  const { data: agentsData, isSuccess: agentsLoaded } = useSwarmAgents(projectId, {
    refetchInterval: (query) => {
      const agents = query.state.data?.agents
      if (!agents || agents.length === 0) return 5000
      return agents.some(a => a.alive) ? 2000 : 5000
    },
  })
  const availableAgents = agentsData?.agents ?? []

  // TanStack Query mutations
  const stopAgentMutation = useStopSwarmAgent()
  const sendInputMutation = useSendSwarmInput()

  // Keep ref in sync for use in scroll handler
  autoScrollRef.current = autoScroll

  // Clean up error timer on unmount
  useEffect(() => {
    return () => {
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
    }
  }, [])

  // Derived state from real-time agent polling (not stale isRunning prop)
  const anyAgentAlive = availableAgents.some(a => a.alive)
  const aliveCount = availableAgents.filter(a => a.alive).length
  const crashedCount = availableAgents.filter(a => !a.alive && a.exit_code != null && a.exit_code !== 0).length
  const canSendInput = anyAgentAlive
  const allStopped = agentsLoaded && availableAgents.length > 0 && !anyAgentAlive

  // Virtual scrolling
  const virtualizer = useVirtualizer({
    count: lines.length,
    getScrollElement: () => containerRef.current,
    estimateSize: () => 20,
    overscan: 30,
  })

  // Auto-scroll to bottom when new lines arrive
  useEffect(() => {
    if (autoScroll && lines.length > 0) {
      virtualizer.scrollToIndex(lines.length - 1, { align: 'end' })
    }
  }, [lines.length, autoScroll, virtualizer])

  // Detect user scroll to toggle auto-scroll
  const handleScroll = useCallback(() => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    const nearBottom = scrollHeight - scrollTop - clientHeight < 50
    setAutoScroll(nearBottom)
  }, [])

  // Reset lines when agent filter changes
  useEffect(() => {
    setLines([])
    offsetRef.current = 0
  }, [agentFilter])

  // Poll output
  useEffect(() => {
    if (!projectId || !fetchOutput) return

    setLines([])
    setPollError(false)
    offsetRef.current = 0
    let idleCount = 0
    let errorCount = 0
    let cancelled = false
    const { signal, abort } = createAbortable()

    const poll = async () => {
      if (cancelled) return
      try {
        const data = await fetchOutput(projectId, offsetRef.current, agentFilter, { signal })
        if (data.lines && data.lines.length > 0) {
          offsetRef.current = data.next_offset
          startTransition(() => {
            setLines((prev) => {
              const next = [...prev, ...data.lines]
              return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
            })
          })
          idleCount = 0
        } else {
          idleCount++
        }
        if (errorCount > 0) {
          errorCount = 0
          setPollError(false)
        }
      } catch (e) {
        if (e.name === 'AbortError') return
        console.warn('Terminal output poll error:', e)
        idleCount++
        errorCount++
        if (errorCount >= 3) setPollError(true)
      }
      if (!cancelled) {
        const delay = idleCount < 3 ? 1500 : idleCount < 10 ? 3000 : 5000
        intervalRef.current = setTimeout(poll, delay)
      }
    }

    poll()

    return () => {
      cancelled = true
      abort()
      if (intervalRef.current) clearTimeout(intervalRef.current)
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
    }
  }, [projectId, fetchOutput, agentFilter])

  const handleSendInput = async () => {
    const text = inputText.trim()
    if (!text) return
    if (text.length > 1000) {
      setInputError('Input must be 1000 characters or less')
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
      errorTimerRef.current = setTimeout(() => setInputError(null), 3000)
      return
    }

    setInputError(null)
    setInputText('')
    inputRef.current?.focus()

    // Echo locally
    setLines((prev) => {
      const prefix = agentFilter ? `[${agentFilter}] > ` : '> '
      const next = [...prev, `${prefix}${text}`]
      return next.length > MAX_LINES ? next.slice(-MAX_LINES) : next
    })

    try {
      await sendInputMutation.mutateAsync({ projectId, text, agent: agentFilter })
    } catch (e) {
      setInputError(e.message)
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
      errorTimerRef.current = setTimeout(() => setInputError(null), 3000)
    }
  }

  const handleInputKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendInput()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      setInputText('')
      setInputError(null)
    }
  }

  // Ref to latest handleSendInput to avoid stale closure in keyboard handler
  const handleSendInputRef = useRef(handleSendInput)
  handleSendInputRef.current = handleSendInput

  // Global keyboard shortcuts for terminal
  useEffect(() => {
    const handler = (e) => {
      const isMod = e.ctrlKey || e.metaKey

      // Ctrl+L: Clear terminal output
      if (isMod && e.key === 'l') {
        e.preventDefault()
        setLines([])
        offsetRef.current = 0
      }

      // Ctrl+Enter: Focus input and send (if input has text)
      if (isMod && e.key === 'Enter') {
        e.preventDefault()
        if (inputRef.current) {
          inputRef.current.focus()
          handleSendInputRef.current()
        }
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const handleStopAgent = useCallback(async (agentName) => {
    setStoppingAgent(agentName)
    try {
      await stopAgentMutation.mutateAsync({ projectId, agentName })
    } catch (e) {
      setInputError(`Failed to stop ${agentName}: ${e.message}`)
      if (errorTimerRef.current) clearTimeout(errorTimerRef.current)
      errorTimerRef.current = setTimeout(() => setInputError(null), 3000)
    } finally {
      setStoppingAgent(null)
    }
  }, [projectId, stopAgentMutation])

  // Agent tab refs for keyboard navigation
  const agentTabRefs = useRef({})

  // All tab IDs in order: [null (All), agent1, agent2, ...]
  const tabIds = useMemo(() => [null, ...availableAgents.map(a => a.name)], [availableAgents])

  const handleAgentTabKeyDown = useCallback((e) => {
    const currentIdx = tabIds.indexOf(agentFilter)
    if (currentIdx === -1) return
    let nextIdx = -1

    if (e.key === 'ArrowRight') nextIdx = (currentIdx + 1) % tabIds.length
    else if (e.key === 'ArrowLeft') nextIdx = (currentIdx - 1 + tabIds.length) % tabIds.length
    else if (e.key === 'Home') nextIdx = 0
    else if (e.key === 'End') nextIdx = tabIds.length - 1
    else return

    e.preventDefault()
    const nextId = tabIds[nextIdx]
    setAgentFilter(nextId)
    const refKey = nextId === null ? '__all__' : nextId
    agentTabRefs.current[refKey]?.focus()
  }, [agentFilter, tabIds])

  // LED class based on agent state
  const agentLedClass = (agent) => {
    if (agent.alive) return 'led-active animate-pulse'
    if (agent.exit_code != null && agent.exit_code !== 0) return 'led-danger'
    return 'led-inactive'
  }

  const agentLedLabel = (agent) => {
    if (agent.alive) return 'running'
    if (agent.exit_code != null && agent.exit_code !== 0) return `crashed (exit ${agent.exit_code})`
    return 'stopped'
  }

  const agentTabColor = (name) => AGENT_NEON_COLORS[name] || ''

  // Export terminal output as text file
  const handleExportOutput = useCallback(() => {
    const text = lines.map(line => stripAnsi(line)).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `terminal-output-${projectId}-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }, [lines, projectId])

  // Detect error lines indices (memoized for perf with large buffers)
  const errorIndices = useMemo(() => {
    const indices = []
    for (let i = 0; i < lines.length; i++) {
      if (ERROR_PATTERN.test(stripAnsi(lines[i]))) indices.push(i)
    }
    return indices
  }, [lines])

  // Jump to next error from current scroll position
  const jumpToNextError = useCallback(() => {
    if (errorIndices.length === 0) return
    // Find the first visible item index
    const visibleItems = virtualizer.getVirtualItems()
    const currentIdx = visibleItems.length > 0 ? visibleItems[Math.floor(visibleItems.length / 2)].index : 0
    // Find next error after current position
    const nextError = errorIndices.find(i => i > currentIdx) ?? errorIndices[0]
    setAutoScroll(false)
    virtualizer.scrollToIndex(nextError, { align: 'center' })
  }, [errorIndices, virtualizer])

  // Is a specific line an error line?
  const isErrorLine = useCallback((index) => {
    return ERROR_PATTERN.test(stripAnsi(lines[index] || ''))
  }, [lines])

  // Contextual empty state
  const emptyState = () => {
    if (isRunning || anyAgentAlive) {
      return {
        message: agentFilter ? `Waiting for ${agentFilter} output...` : 'Waiting for agent output...',
        showSpinner: true,
        hint: null,
      }
    }
    if (allStopped) {
      return {
        message: 'All agents have stopped.',
        showSpinner: false,
        hint: 'Launch a new swarm to see output.',
      }
    }
    return {
      message: 'No output yet.',
      showSpinner: false,
      hint: 'Launch a swarm from the Dashboard tab to get started.',
    }
  }

  return (
    <div className="retro-panel border border-retro-border rounded flex flex-col relative">
      <div className="flex items-center justify-between px-2 sm:px-4 py-2 border-b border-retro-border">
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <h2 className="text-[10px] sm:text-xs uppercase tracking-[0.15em] sm:tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono shrink-0">Terminal</h2>
          {agentsLoaded && availableAgents.length > 0 && (
            <span className="text-[10px] font-mono text-zinc-600" role="status" aria-label={`${aliveCount} of ${availableAgents.length} agents running`}>
              {aliveCount > 0 ? (
                <span className="text-crt-green">{aliveCount}/{availableAgents.length} active</span>
              ) : (
                <span>{availableAgents.length} stopped</span>
              )}
              {crashedCount > 0 && (
                <span className="text-signal-red ml-1">({crashedCount} crashed)</span>
              )}
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-600 font-mono">{lines.length.toLocaleString()} lines</span>
          {lines.length > 0 && (
            <button
              onClick={handleExportOutput}
              className="text-[11px] text-zinc-500 hover:text-crt-green bg-transparent border-0 cursor-pointer font-mono"
              title="Export output as text file"
              aria-label="Export terminal output"
            >
              Export
            </button>
          )}
          <button
            onClick={() => { setLines([]); offsetRef.current = 0 }}
            className="text-[11px] text-zinc-500 hover:text-crt-green bg-transparent border-0 cursor-pointer font-mono"
          >
            Clear
          </button>
        </div>
      </div>

      {/* Swarm completion banner */}
      {allStopped && lines.length > 0 && (
        <div className="px-3 py-1.5 border-b border-retro-border flex items-center gap-2 text-[11px] font-mono bg-retro-grid/30" role="status">
          {crashedCount > 0 ? (
            <span className="text-signal-red">Swarm finished — {crashedCount} agent{crashedCount !== 1 ? 's' : ''} crashed</span>
          ) : (
            <span className="text-crt-green">Swarm completed — all agents exited normally</span>
          )}
        </div>
      )}

      {/* Agent sub-tabs */}
      {!agentsLoaded && isRunning && (
        <div className="px-3 py-2 border-b border-retro-border flex items-center gap-2" role="status">
          <div className="flex gap-1.5">
            {[1, 2, 3, 4].map(i => (
              <div key={i} className="w-14 h-5 rounded bg-retro-grid/50 animate-pulse" style={{ animationDelay: `${i * 150}ms` }} />
            ))}
          </div>
          <span className="text-[11px] text-zinc-600 font-mono animate-pulse">Discovering agents...</span>
        </div>
      )}
      {availableAgents.length > 0 && (
        <div className="flex items-center gap-1 px-3 py-1.5 border-b border-retro-border overflow-x-auto group/tabs">
          <div role="tablist" aria-label="Agent filter" className="flex items-center gap-1">
            <button
              ref={(el) => { agentTabRefs.current['__all__'] = el }}
              role="tab"
              aria-selected={agentFilter === null}
              tabIndex={agentFilter === null ? 0 : -1}
              onClick={() => setAgentFilter(null)}
              onKeyDown={handleAgentTabKeyDown}
              className={`px-2.5 py-1 rounded text-[11px] font-mono cursor-pointer border transition-colors ${
                agentFilter === null
                  ? 'bg-retro-grid text-crt-green border-crt-green/30'
                  : 'text-zinc-500 hover:text-zinc-300 bg-transparent border-transparent'
              }`}
            >
              All ({availableAgents.length})
            </button>
            {availableAgents.map((a) => (
              <button
                key={a.name}
                ref={(el) => { agentTabRefs.current[a.name] = el }}
                role="tab"
                aria-selected={agentFilter === a.name}
                tabIndex={agentFilter === a.name ? 0 : -1}
                onClick={() => setAgentFilter(a.name)}
                onKeyDown={handleAgentTabKeyDown}
                title={`${a.name}${AGENT_ROLES[a.name] ? ` — ${AGENT_ROLES[a.name]}` : ''} (${agentLedLabel(a)})`}
                className={`px-2.5 py-1 rounded text-[11px] font-mono cursor-pointer border transition-colors flex items-center gap-1.5 ${
                  agentFilter === a.name
                    ? 'bg-retro-grid border-crt-green/30 ' + (agentTabColor(a.name) || 'text-crt-green')
                    : 'text-zinc-500 hover:text-zinc-300 bg-transparent border-transparent'
                }`}
              >
                <span
                  className={`inline-block w-2 h-2 rounded-full shrink-0 ${agentLedClass(a)}`}
                  role="img"
                  aria-label={agentLedLabel(a)}
                />
                {a.name}
              </button>
            ))}
          </div>
          {availableAgents.some(a => a.alive) && (
            <div className="flex items-center gap-1 ml-1" aria-label="Agent controls">
              {agentFilter && (
                <button
                  onClick={() => setDirectiveAgent(directiveAgent === agentFilter ? null : agentFilter)}
                  className={`text-[10px] font-mono cursor-pointer transition-opacity bg-transparent border-0 px-1 py-0.5 rounded ${
                    directiveAgent === agentFilter ? 'text-crt-cyan opacity-100' : 'text-zinc-600 hover:text-crt-cyan opacity-0 group-hover/tabs:opacity-100 focus:opacity-100'
                  }`}
                  title={`Send directive to ${agentFilter}`}
                  aria-label={`Send directive to ${agentFilter}`}
                  aria-expanded={directiveAgent === agentFilter}
                >
                  Direct
                </button>
              )}
              {availableAgents.filter(a => a.alive).map(a => (
                <button
                  key={a.name}
                  onClick={() => handleStopAgent(a.name)}
                  disabled={stoppingAgent === a.name}
                  className="text-[10px] text-zinc-600 hover:text-signal-red cursor-pointer opacity-0 group-hover/tabs:opacity-100 focus:opacity-100 transition-opacity bg-transparent border-0 p-0 leading-none"
                  title={`Stop ${a.name}`}
                  aria-label={`Stop ${a.name}`}
                >
                  {stoppingAgent === a.name ? '...' : '✕'}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Inline directive panel */}
      {directiveAgent && (
        <div className="px-3 py-2 border-b border-retro-border">
          <DirectivePanel
            projectId={projectId}
            agentName={directiveAgent}
            onClose={() => setDirectiveAgent(null)}
          />
        </div>
      )}

      {pollError && (
        <div className="px-3 py-1.5 bg-signal-red/10 border-b border-signal-red/20 flex items-center gap-2 text-[11px] font-mono text-signal-red" role="alert">
          <span>Connection lost — retrying automatically</span>
        </div>
      )}

      {/* Virtualized terminal output */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="font-mono text-[11px] sm:text-xs leading-5 overflow-y-auto max-h-72 sm:max-h-96 min-h-[120px] sm:min-h-[200px] bg-retro-dark flex-1"
        role="log"
        aria-label="Terminal output"
      >
        {lines.length === 0 ? (
          (() => {
            const es = emptyState()
            return (
              <div className="text-zinc-600 text-center py-8 flex flex-col items-center gap-2 px-2 sm:px-3">
                {es.showSpinner && (
                  <div className="w-5 h-5 border-2 border-crt-green/30 border-t-crt-green rounded-full animate-spin" role="img" aria-label="Loading" />
                )}
                <span className="text-sm">{es.message}</span>
                {es.hint && <span className="text-[11px] text-zinc-700">{es.hint}</span>}
              </div>
            )
          })()
        ) : (
          <div
            style={{
              height: `${virtualizer.getTotalSize()}px`,
              width: '100%',
              position: 'relative',
            }}
          >
            {virtualizer.getVirtualItems().map((virtualRow) => (
              <div
                key={virtualRow.index}
                data-index={virtualRow.index}
                ref={virtualizer.measureElement}
                style={{
                  position: 'absolute',
                  top: 0,
                  left: 0,
                  width: '100%',
                  transform: `translateY(${virtualRow.start}px)`,
                }}
                className={`whitespace-pre-wrap break-all px-2 sm:px-3 ${isErrorLine(virtualRow.index) ? 'bg-signal-red/10 border-l-2 border-signal-red/40' : ''}`}
              >
                {parseAnsiLine(lines[virtualRow.index]).map((seg, j) => (
                  <span key={j} className={seg.className}>{seg.text}</span>
                ))}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Floating action buttons */}
      {lines.length > 0 && (
        <div className="absolute bottom-24 right-6 z-10 flex flex-col gap-1.5">
          {errorIndices.length > 0 && (
            <button
              onClick={jumpToNextError}
              className="px-2.5 py-1 rounded bg-signal-red/20 border border-signal-red/30 text-[10px] font-mono text-signal-red hover:bg-signal-red/30 cursor-pointer transition-colors shadow-lg"
              aria-label={`Jump to next error (${errorIndices.length} errors)`}
            >
              {errorIndices.length} error{errorIndices.length !== 1 ? 's' : ''} ↓
            </button>
          )}
          {!autoScroll && (
            <button
              onClick={() => {
                setAutoScroll(true)
                virtualizer.scrollToIndex(lines.length - 1, { align: 'end' })
              }}
              className="px-2.5 py-1 rounded bg-retro-grid/90 border border-retro-border text-[10px] font-mono text-crt-green hover:bg-retro-border cursor-pointer transition-colors shadow-lg"
              aria-label="Scroll to bottom"
            >
              Scroll to bottom
            </button>
          )}
        </div>
      )}

      {/* Input bar */}
      <div className="flex items-center gap-1.5 sm:gap-2 px-2 sm:px-3 py-1.5 sm:py-2 border-t border-retro-border bg-retro-dark/50">
        <span className="text-crt-green font-mono text-[10px] sm:text-xs select-none shrink-0" aria-hidden="true">
          {agentFilter ? `[${agentFilter}]` : '>'}
        </span>
        <input
          ref={inputRef}
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleInputKeyDown}
          disabled={!canSendInput}
          placeholder={
            canSendInput
              ? `Send to ${agentFilter || 'all agents'} (Enter to submit)`
              : allStopped
                ? 'All agents stopped'
                : 'Waiting for agents...'
          }
          className="retro-input flex-1 px-1.5 sm:px-2 py-1 text-[11px] sm:text-xs font-mono disabled:opacity-40 disabled:cursor-not-allowed min-w-0"
          aria-label={`Terminal input${agentFilter ? ` for ${agentFilter}` : ''}`}
          aria-invalid={inputError ? 'true' : undefined}
          aria-describedby={inputError ? 'terminal-input-error' : undefined}
        />
        <button
          onClick={handleSendInput}
          disabled={!canSendInput || !inputText.trim()}
          className="px-2 sm:px-2.5 py-1 text-[11px] sm:text-xs font-mono rounded bg-transparent border border-crt-green/30 text-crt-green hover:bg-crt-green/10 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors shrink-0"
          aria-label="Send input"
        >
          Send
        </button>
      </div>
      {inputError && (
        <div id="terminal-input-error" className="px-3 py-1.5 text-[10px] text-signal-red font-mono bg-signal-red/5 flex items-center gap-1.5" role="alert">
          <span aria-hidden="true">!</span>
          <span>{inputError}</span>
        </div>
      )}
    </div>
  )
}

export { stripAnsi, parseAnsiLine }
