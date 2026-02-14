import { useState, useEffect, useRef, useCallback, useMemo, memo, useDeferredValue } from 'react'
import { AGENT_NAMES, AGENT_LOG_COLORS } from '../lib/constants'
import { LogViewerSkeleton } from './Skeleton'
import { useSafeToast } from './Toast'
import { useLogs, useLogSearch } from '../hooks/useSwarmQuery'

const levels = ['all', 'INFO', 'WARN', 'ERROR', 'DEBUG']
const levelRegex = /\b(INFO|WARN|ERROR|DEBUG)\b/
const ROW_HEIGHT = 22
const OVERSCAN = 15
const VIRTUALIZE_THRESHOLD = 200
const FILTER_STORAGE_KEY = 'lu_log_filters'

function saveLogFilters(projectId, filters) {
  try {
    const stored = JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) || '{}')
    stored[projectId] = filters
    localStorage.setItem(FILTER_STORAGE_KEY, JSON.stringify(stored))
  } catch { /* ignore */ }
}

function loadLogFilters(projectId) {
  try {
    const stored = JSON.parse(localStorage.getItem(FILTER_STORAGE_KEY) || '{}')
    return stored[projectId] || null
  } catch { return null }
}

function HighlightedText({ text, search }) {
  if (!search) return <span className="text-zinc-400">{text}</span>

  const escaped = search.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const splitRegex = new RegExp(`(${escaped})`, 'gi')
  const matchRegex = new RegExp(`^${escaped}$`, 'i')
  const parts = text.split(splitRegex)

  if (parts.length === 1) return <span className="text-zinc-400">{text}</span>

  return (
    <span className="text-zinc-400">
      {parts.map((part, i) =>
        matchRegex.test(part) ? (
          <mark key={i} className="bg-crt-amber/30 text-crt-amber rounded-sm px-0.5">{part}</mark>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </span>
  )
}

export default memo(function LogViewer({ projectId, wsEvents }) {
  const toast = useSafeToast()
  const [logs, setLogs] = useState([])
  const savedFilters = useMemo(() => loadLogFilters(projectId), [projectId])
  const [filter, setFilter] = useState(savedFilters?.agent || 'all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [searchText, setSearchText] = useState(savedFilters?.search || '')
  const [levelFilter, setLevelFilter] = useState(savedFilters?.level || 'all')
  const [fromDate, setFromDate] = useState(savedFilters?.fromDate || '')
  const [toDate, setToDate] = useState(savedFilters?.toDate || '')
  const containerRef = useRef(null)
  const lastWsTime = useRef(0)
  const [isLive, setIsLive] = useState(false)
  const [scrollTop, setScrollTop] = useState(0)
  const [containerHeight, setContainerHeight] = useState(400)
  const debouncedSearch = useDeferredValue(searchText)

  // Persist filters to localStorage
  useEffect(() => {
    saveLogFilters(projectId, { agent: filter, search: searchText, level: levelFilter, fromDate, toDate })
  }, [projectId, filter, searchText, levelFilter, fromDate, toDate])

  const hasDateFilter = fromDate || toDate

  // Build search params for TanStack Query
  const searchParams = useMemo(() => {
    const params = {}
    if (debouncedSearch) params.q = debouncedSearch
    if (filter !== 'all') params.agent = filter
    if (levelFilter !== 'all') params.level = levelFilter
    if (fromDate) params.from_date = fromDate
    if (toDate) params.to_date = toDate
    return params
  }, [debouncedSearch, filter, levelFilter, fromDate, toDate])

  // TanStack Query: initial log load (when no date filters)
  const { data: logsData, isLoading: logsLoading, error: logsError } = useLogs(projectId, 200, {
    enabled: !!projectId && !hasDateFilter,
  })

  // TanStack Query: server-side search (when date filters active)
  const { data: searchData, isFetching: isSearching, error: searchError } = useLogSearch(
    projectId, searchParams, { enabled: !!projectId && !!hasDateFilter }
  )

  // Sync TanStack Query data to local state for WS appending
  useEffect(() => {
    if (!hasDateFilter && logsData) {
      const flat = (logsData.logs || []).flatMap((entry) =>
        entry.lines.map((line, i) => ({
          id: `${entry.agent}-${i}-${Date.now()}`,
          agent: entry.agent,
          text: line,
        }))
      )
      setLogs(flat)
    }
  }, [logsData, hasDateFilter])

  useEffect(() => {
    if (hasDateFilter && searchData) {
      const results = (searchData.results || []).map((r, i) => ({
        id: `search-${i}-${Date.now()}`,
        agent: r.agent,
        text: r.text,
      }))
      setLogs(results)
    }
  }, [searchData, hasDateFilter])

  // Show errors via toast
  useEffect(() => {
    if (logsError) toast(`Failed to load logs: ${logsError.message}`, 'error')
  }, [logsError])
  useEffect(() => {
    if (searchError) toast(`Log search failed: ${searchError.message}`, 'error')
  }, [searchError])

  // Append WebSocket log events (only when not in search mode)
  useEffect(() => {
    if (wsEvents?.type === 'log') {
      lastWsTime.current = Date.now()
      setIsLive(true)

      if (!hasDateFilter) {
        const newEntries = wsEvents.lines.map((line, i) => ({
          id: `${wsEvents.agent}-ws-${Date.now()}-${i}`,
          agent: wsEvents.agent,
          text: line,
        }))
        setLogs((prev) => [...prev, ...newEntries].slice(-1000))
      }
    }
  }, [wsEvents, hasDateFilter])

  // LIVE indicator timeout
  useEffect(() => {
    const timer = setInterval(() => {
      if (Date.now() - lastWsTime.current > 5000) {
        setIsLive(false)
      }
    }, 2000)
    return () => clearInterval(timer)
  }, [])

  // Client-side filtering (only when not using server search)
  const filtered = useMemo(() => {
    if (hasDateFilter) return logs
    return logs.filter((l) => {
      if (filter !== 'all' && l.agent !== filter) return false
      if (levelFilter !== 'all') {
        const match = l.text.match(levelRegex)
        if (!match || match[1] !== levelFilter) return false
      }
      if (debouncedSearch) {
        return l.text.toLowerCase().includes(debouncedSearch.toLowerCase())
      }
      return true
    })
  }, [logs, filter, levelFilter, debouncedSearch, hasDateFilter])

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight
    }
  }, [filtered.length, autoScroll])

  // Track container size for virtual scroll
  useEffect(() => {
    const el = containerRef.current
    if (!el) return
    const ro = new ResizeObserver(([entry]) => {
      setContainerHeight(entry.contentRect.height)
    })
    ro.observe(el)
    return () => ro.disconnect()
  }, [])

  const handleScroll = useCallback(() => {
    if (containerRef.current) {
      setScrollTop(containerRef.current.scrollTop)
    }
  }, [])

  // Virtual scroll range calculation
  const virtualRange = useMemo(() => {
    const totalHeight = filtered.length * ROW_HEIGHT
    const startIdx = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - OVERSCAN)
    const visibleCount = Math.ceil(containerHeight / ROW_HEIGHT)
    const endIdx = Math.min(filtered.length, startIdx + visibleCount + OVERSCAN * 2)
    return { startIdx, endIdx, totalHeight }
  }, [filtered.length, scrollTop, containerHeight])

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

  if (logsLoading && !hasDateFilter) {
    return <LogViewerSkeleton />
  }

  return (
    <div className="retro-panel border border-retro-border rounded flex flex-col h-full animate-fade-in">
      {/* Agent filter row */}
      <div className="flex items-center gap-2 px-3 py-2 border-b border-retro-border flex-wrap">
        <button
          onClick={() => setFilter('all')}
          aria-pressed={filter === 'all'}
          aria-label="Filter by all agents"
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
            aria-pressed={filter === a}
            aria-label={`Filter by ${a}`}
            className={`px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer border-0 font-mono ${
              filter === a ? 'bg-retro-grid text-zinc-100' : `${AGENT_LOG_COLORS[a]?.label || 'text-zinc-500'} hover:bg-retro-grid bg-transparent`
            }`}
          >
            {a}
          </button>
        ))}

        <div className="flex-1" />

        {isLive && !hasDateFilter && (
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
          aria-label="Search logs"
          className="retro-input px-2 py-1 text-xs w-28 sm:w-40"
        />
        {levels.map((lvl) => (
          <button
            key={lvl}
            onClick={() => setLevelFilter(lvl)}
            aria-pressed={levelFilter === lvl}
            aria-label={`Filter by ${lvl === 'all' ? 'all levels' : lvl + ' level'}`}
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

      {/* Log output - virtualized for large lists */}
      <div
        ref={containerRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto font-mono text-xs min-h-48 bg-retro-dark"
      >
        {filtered.length === 0 && (
          <div className="text-zinc-600 text-center py-8">No logs</div>
        )}
        {filtered.length > 0 && filtered.length <= VIRTUALIZE_THRESHOLD && (
          <div className="p-3">
            {filtered.map((entry) => {
              const color = AGENT_LOG_COLORS[entry.agent] || { label: 'text-zinc-500', bg: '' }
              return (
                <div key={entry.id} className={`py-0.5 px-2 rounded ${color.bg}`}>
                  <span className={`font-semibold ${color.label}`}>[{entry.agent}]</span>{' '}
                  <HighlightedText text={entry.text} search={debouncedSearch} />
                </div>
              )
            })}
          </div>
        )}
        {filtered.length > VIRTUALIZE_THRESHOLD && (
          <div style={{ height: virtualRange.totalHeight, position: 'relative' }}>
            {filtered.slice(virtualRange.startIdx, virtualRange.endIdx).map((entry, i) => {
              const color = AGENT_LOG_COLORS[entry.agent] || { label: 'text-zinc-500', bg: '' }
              return (
                <div
                  key={entry.id}
                  className={`px-3 rounded ${color.bg}`}
                  style={{
                    position: 'absolute',
                    top: (virtualRange.startIdx + i) * ROW_HEIGHT,
                    height: ROW_HEIGHT,
                    left: 0,
                    right: 0,
                    display: 'flex',
                    alignItems: 'center',
                  }}
                >
                  <span className={`font-semibold ${color.label} shrink-0`}>[{entry.agent}]</span>
                  <span className="ml-1 truncate"><HighlightedText text={entry.text} search={debouncedSearch} /></span>
                </div>
              )
            })}
          </div>
        )}
      </div>
    </div>
  )
})
