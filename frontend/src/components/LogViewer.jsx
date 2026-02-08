import { useState, useEffect, useRef, useCallback, useMemo } from 'react'
import { getLogs, searchLogs } from '../lib/api'
import { AGENT_NAMES, AGENT_LOG_COLORS } from '../lib/constants'

const levels = ['all', 'INFO', 'WARN', 'ERROR', 'DEBUG']
const levelRegex = /\b(INFO|WARN|ERROR|DEBUG)\b/

export default function LogViewer({ projectId, wsEvents }) {
  const [logs, setLogs] = useState([])
  const [filter, setFilter] = useState('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [searchText, setSearchText] = useState('')
  const [levelFilter, setLevelFilter] = useState('all')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [isSearching, setIsSearching] = useState(false)
  const containerRef = useRef(null)
  const lastWsTime = useRef(0)
  const [isLive, setIsLive] = useState(false)

  const hasDateFilter = fromDate || toDate
  const hasServerFilter = hasDateFilter

  // Load initial logs (no date filters)
  const loadLogs = useCallback(async () => {
    try {
      const data = await getLogs(projectId, 200)
      const flat = (data.logs || []).flatMap((entry) =>
        entry.lines.map((line, i) => ({
          id: `${entry.agent}-${i}-${Date.now()}`,
          agent: entry.agent,
          text: line,
        }))
      )
      setLogs(flat)
    } catch (e) {
      console.warn('Failed to load logs:', e)
    }
  }, [projectId])

  // Server-side search (when date filters are active)
  const runSearch = useCallback(async () => {
    setIsSearching(true)
    try {
      const params = {}
      if (searchText) params.q = searchText
      if (filter !== 'all') params.agent = filter
      if (levelFilter !== 'all') params.level = levelFilter
      if (fromDate) params.from_date = fromDate
      if (toDate) params.to_date = toDate

      const data = await searchLogs(projectId, params)
      const results = (data.results || []).map((r, i) => ({
        id: `search-${i}-${Date.now()}`,
        agent: r.agent,
        text: r.text,
      }))
      setLogs(results)
    } catch (e) {
      console.warn('Failed to search logs:', e)
    } finally {
      setIsSearching(false)
    }
  }, [projectId, searchText, filter, levelFilter, fromDate, toDate])

  useEffect(() => {
    if (hasServerFilter) {
      runSearch()
    } else {
      loadLogs()
    }
  }, [hasServerFilter, runSearch, loadLogs])

  // Append WebSocket log events (only when not in search mode)
  useEffect(() => {
    if (wsEvents?.type === 'log') {
      lastWsTime.current = Date.now()
      setIsLive(true)

      if (!hasServerFilter) {
        const newEntries = wsEvents.lines.map((line, i) => ({
          id: `${wsEvents.agent}-ws-${Date.now()}-${i}`,
          agent: wsEvents.agent,
          text: line,
        }))
        setLogs((prev) => [...prev, ...newEntries].slice(-1000))
      }
    }
  }, [wsEvents, hasServerFilter])

  // LIVE indicator timeout
  useEffect(() => {
    const timer = setInterval(() => {
      if (Date.now() - lastWsTime.current > 5000) {
        setIsLive(false)
      }
    }, 2000)
    return () => clearInterval(timer)
  }, [])

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [logs, autoScroll])

  // Client-side filtering (only when not using server search)
  const filtered = useMemo(() => {
    if (hasServerFilter) return logs
    return logs.filter((l) => {
      if (filter !== 'all' && l.agent !== filter) return false
      if (levelFilter !== 'all') {
        const match = l.text.match(levelRegex)
        if (!match || match[1] !== levelFilter) return false
      }
      if (searchText) {
        return l.text.toLowerCase().includes(searchText.toLowerCase())
      }
      return true
    })
  }, [logs, filter, levelFilter, searchText, hasServerFilter])

  const handleCopy = () => {
    const text = filtered.map((l) => `[${l.agent}] ${l.text}`).join('\n')
    navigator.clipboard.writeText(text).catch(() => {})
  }

  const handleDownload = () => {
    const text = filtered.map((l) => `[${l.agent}] ${l.text}`).join('\n')
    const blob = new Blob([text], { type: 'text/plain' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `logs-${projectId}-${Date.now()}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="retro-panel border border-retro-border rounded flex flex-col h-full">
      {/* Agent filter row */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-retro-border flex-wrap">
        <button
          onClick={() => setFilter('all')}
          className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer border-0 font-mono ${
            filter === 'all' ? 'bg-retro-grid text-crt-green border border-crt-green/30' : 'text-zinc-500 hover:text-zinc-300 bg-transparent'
          }`}
        >
          All
        </button>
        {AGENT_NAMES.map((a) => (
          <button
            key={a}
            onClick={() => setFilter(a)}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer border-0 font-mono ${
              filter === a ? 'bg-retro-grid text-zinc-100' : `${AGENT_LOG_COLORS[a]?.label || 'text-zinc-500'} hover:bg-retro-grid bg-transparent`
            }`}
          >
            {a}
          </button>
        ))}

        <div className="flex-1" />

        {isLive && !hasServerFilter && (
          <span className="flex items-center gap-1 text-[10px] font-mono text-crt-green">
            <span className="w-1.5 h-1.5 rounded-full bg-crt-green animate-pulse" />
            LIVE
          </span>
        )}

        <label className="flex items-center gap-1.5 text-xs text-zinc-500 cursor-pointer font-mono">
          <input
            type="checkbox"
            checked={autoScroll}
            onChange={(e) => setAutoScroll(e.target.checked)}
            className="accent-crt-green"
          />
          Auto-scroll
        </label>
      </div>

      {/* Search + Level filter + Date range + actions row */}
      <div className="flex items-center gap-2 px-3 py-1.5 border-b border-retro-border flex-wrap">
        <input
          type="text"
          value={searchText}
          onChange={(e) => setSearchText(e.target.value)}
          placeholder="Search logs..."
          className="retro-input px-2 py-1 text-xs w-40"
        />
        {levels.map((lvl) => (
          <button
            key={lvl}
            onClick={() => setLevelFilter(lvl)}
            className={`px-2 py-0.5 rounded text-[10px] font-medium transition-colors cursor-pointer border-0 font-mono ${
              levelFilter === lvl ? 'bg-retro-grid text-crt-green border border-crt-green/30' : 'text-zinc-500 hover:text-zinc-300 bg-transparent'
            }`}
          >
            {lvl === 'all' ? 'All' : lvl}
          </button>
        ))}

        <input
          type="date"
          value={fromDate}
          onChange={(e) => setFromDate(e.target.value)}
          className="retro-input px-1.5 py-0.5 text-[10px] font-mono w-28"
          aria-label="From date"
          title="From date"
        />
        <input
          type="date"
          value={toDate}
          onChange={(e) => setToDate(e.target.value)}
          className="retro-input px-1.5 py-0.5 text-[10px] font-mono w-28"
          aria-label="To date"
          title="To date"
        />
        {hasDateFilter && (
          <button
            onClick={() => { setFromDate(''); setToDate('') }}
            className="text-[10px] text-zinc-500 hover:text-signal-red bg-transparent border-0 cursor-pointer font-mono"
            aria-label="Clear date filter"
          >
            Clear dates
          </button>
        )}

        <div className="flex-1" />

        {isSearching && (
          <span className="text-[10px] text-zinc-500 font-mono animate-pulse">Searching...</span>
        )}

        <button
          onClick={handleCopy}
          title="Copy logs"
          aria-label="Copy logs"
          className="p-1 rounded text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <rect x="5" y="5" width="9" height="9" rx="1" />
            <path d="M11 5V3a1 1 0 00-1-1H3a1 1 0 00-1 1v7a1 1 0 001 1h2" />
          </svg>
        </button>
        <button
          onClick={handleDownload}
          title="Download logs"
          aria-label="Download logs"
          className="p-1 rounded text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
        >
          <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M8 2v9M4 8l4 4 4-4" />
            <path d="M2 13h12" />
          </svg>
        </button>
      </div>

      {/* Log output */}
      <div
        ref={containerRef}
        className="flex-1 overflow-y-auto font-mono text-xs p-3 min-h-48 bg-retro-dark"
      >
        {filtered.length === 0 && (
          <div className="text-zinc-600 text-center py-8">No logs</div>
        )}
        {filtered.map((entry) => {
          const color = AGENT_LOG_COLORS[entry.agent] || { label: 'text-zinc-500', bg: '' }
          return (
            <div key={entry.id} className={`py-0.5 px-2 rounded ${color.bg}`}>
              <span className={`font-semibold ${color.label}`}>[{entry.agent}]</span>{' '}
              <span className="text-zinc-400">{entry.text}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
