import { useState, useEffect, useRef } from 'react'
import { sendSwarmInput } from '../lib/api'

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
  const containerRef = useRef(null)
  const offsetRef = useRef(0)
  const intervalRef = useRef(null)
  const inputRef = useRef(null)

  useEffect(() => {
    if (!projectId || !fetchOutput) return

    setLines([])
    offsetRef.current = 0

    const poll = async () => {
      try {
        const data = await fetchOutput(projectId, offsetRef.current)
        if (data.lines && data.lines.length > 0) {
          setLines((prev) => {
            const next = [...prev, ...data.lines]
            return next.length > 1000 ? next.slice(-1000) : next
          })
          offsetRef.current = data.next_offset
        }
      } catch (e) {
        console.warn('Terminal output poll error:', e)
      }
    }

    poll()
    intervalRef.current = setInterval(poll, 1000)

    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [projectId, fetchOutput])

  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [lines, autoScroll])

  const handleScroll = () => {
    if (!containerRef.current) return
    const { scrollTop, scrollHeight, clientHeight } = containerRef.current
    setAutoScroll(scrollHeight - scrollTop - clientHeight < 50)
  }

  const handleSendInput = async () => {
    const text = inputText.trim()
    if (!text) return
    if (text.length > 1000) {
      setInputError('Input must be 1000 characters or less')
      setTimeout(() => setInputError(null), 3000)
      return
    }

    setInputError(null)
    setInputText('')

    // Echo locally
    setLines((prev) => {
      const next = [...prev, `> ${text}`]
      return next.length > 1000 ? next.slice(-1000) : next
    })

    try {
      await sendSwarmInput(projectId, text)
    } catch (e) {
      setInputError(e.message)
      setTimeout(() => setInputError(null), 3000)
    }
  }

  const handleInputKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSendInput()
    }
  }

  return (
    <div className="retro-panel border border-retro-border rounded flex flex-col">
      <div className="flex items-center justify-between px-4 py-2 border-b border-retro-border">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">Terminal Output</h3>
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-zinc-600 font-mono">{lines.length} lines</span>
          <button
            onClick={() => { setLines([]); offsetRef.current = 0 }}
            className="text-[11px] text-zinc-500 hover:text-crt-green bg-transparent border-0 cursor-pointer font-mono"
          >
            Clear
          </button>
        </div>
      </div>
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="p-3 font-mono text-xs leading-5 overflow-y-auto max-h-96 min-h-[200px] bg-retro-dark flex-1"
        role="log"
        aria-label="Terminal output"
      >
        {lines.length === 0 ? (
          <div className="text-zinc-600 text-center py-8">No output yet</div>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              {parseAnsiLine(line).map((seg, j) => (
                <span key={j} className={seg.className}>{seg.text}</span>
              ))}
            </div>
          ))
        )}
      </div>

      {/* Input bar */}
      <div className="flex items-center gap-2 px-3 py-2 border-t border-retro-border bg-retro-dark/50">
        <span className="text-crt-green font-mono text-xs select-none">&gt;</span>
        <input
          ref={inputRef}
          type="text"
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleInputKeyDown}
          disabled={!isRunning}
          placeholder={isRunning ? 'Type input for swarm...' : 'Swarm not running'}
          className="retro-input flex-1 px-2 py-1 text-xs font-mono disabled:opacity-40 disabled:cursor-not-allowed"
          aria-label="Terminal input"
        />
        <button
          onClick={handleSendInput}
          disabled={!isRunning || !inputText.trim()}
          className="px-2.5 py-1 text-xs font-mono rounded bg-transparent border border-crt-green/30 text-crt-green hover:bg-crt-green/10 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer transition-colors"
          aria-label="Send input"
        >
          Send
        </button>
      </div>
      {inputError && (
        <div className="px-3 py-1 text-[10px] text-signal-red font-mono bg-signal-red/5">
          {inputError}
        </div>
      )}
    </div>
  )
}

export { stripAnsi, parseAnsiLine }
