import { useState, useEffect, useRef } from 'react'

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

export default function TerminalOutput({ projectId, fetchOutput }) {
  const [lines, setLines] = useState([])
  const [autoScroll, setAutoScroll] = useState(true)
  const containerRef = useRef(null)
  const offsetRef = useRef(0)
  const intervalRef = useRef(null)

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
      } catch {
        // Silently ignore polling errors
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
        className="p-3 font-mono text-xs leading-5 overflow-y-auto max-h-96 min-h-[200px] bg-retro-dark"
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
    </div>
  )
}

export { stripAnsi, parseAnsiLine }
