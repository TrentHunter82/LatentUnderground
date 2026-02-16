import { memo, useEffect, useRef, useState } from 'react'
import { useBusMessages } from '../hooks/useSwarmQuery'
import { AGENT_NEON_COLORS } from '../lib/constants'
import MessageComposer from './MessageComposer'

/**
 * Real-time message bus panel showing inter-agent communication.
 * Combines API data with WebSocket real-time updates.
 */
const MessageBusPanel = memo(function MessageBusPanel({ projectId, wsEvents }) {
  const [filters, setFilters] = useState({
    channel: '',
    priority: '',
  })

  const { data, isLoading } = useBusMessages(projectId, filters)
  const [messages, setMessages] = useState([])
  const scrollRef = useRef(null)

  // Load initial messages from API
  useEffect(() => {
    if (data?.messages) {
      setMessages(data.messages)
    }
  }, [data])

  // Handle real-time WebSocket updates
  useEffect(() => {
    if (wsEvents?.type === 'bus_message' && wsEvents.project_id === projectId) {
      setMessages((prev) => {
        // Add new message at the top, limit to 100
        const newMessages = [wsEvents.message, ...prev].slice(0, 100)
        return newMessages
      })
    }
  }, [wsEvents, projectId])

  // Auto-scroll to top when new messages arrive
  useEffect(() => {
    if (scrollRef.current && messages.length > 0) {
      scrollRef.current.scrollTo({ top: 0, behavior: 'smooth' })
    }
  }, [messages.length])

  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">
          MESSAGE BUS
        </h2>
        <div className="flex gap-2">
          <select
            className="retro-input text-xs py-1 px-2"
            value={filters.channel}
            onChange={(e) => setFilters((f) => ({ ...f, channel: e.target.value }))}
            aria-label="Filter by channel"
          >
            <option value="">All Channels</option>
            <option value="critical">Critical</option>
            <option value="general">General</option>
            <option value="lessons">Lessons</option>
            <option value="review">Review</option>
            <option value="handoff">Handoff</option>
          </select>
          <select
            className="retro-input text-xs py-1 px-2"
            value={filters.priority}
            onChange={(e) => setFilters((f) => ({ ...f, priority: e.target.value }))}
            aria-label="Filter by priority"
          >
            <option value="">All Priorities</option>
            <option value="critical">Critical</option>
            <option value="high">High</option>
            <option value="normal">Normal</option>
            <option value="low">Low</option>
          </select>
        </div>
      </div>

      <div
        ref={scrollRef}
        className="h-64 overflow-y-auto space-y-2 scrollbar-thin scrollbar-thumb-zinc-700"
        role="log"
        aria-live="polite"
        aria-label="Message bus feed"
      >
        {isLoading && (
          <div className="text-zinc-500 text-sm animate-pulse">Loading messages...</div>
        )}
        {!isLoading && messages.length === 0 && (
          <div className="text-zinc-500 text-sm text-center py-8">No messages</div>
        )}
        {messages.map((msg) => (
          <MessageItem key={msg.id} message={msg} />
        ))}
      </div>

      {data?.total > messages.length && (
        <div className="text-xs text-zinc-500 mt-2 text-center">
          Showing {messages.length} of {data.total} messages
        </div>
      )}

      {/* Message Composer */}
      <div className="mt-3 pt-3 border-t border-zinc-700/50">
        <MessageComposer projectId={projectId} />
      </div>
    </div>
  )
})

/**
 * Individual message item with agent color coding and priority indicator.
 */
function MessageItem({ message }) {
  const agentColorClass = AGENT_NEON_COLORS[message.from_agent] || 'text-zinc-400'

  const priorityStyles = {
    critical: 'border-l-red-500 bg-red-500/5',
    high: 'border-l-amber-500 bg-amber-500/5',
    normal: 'border-l-zinc-600',
    low: 'border-l-zinc-700 opacity-75',
  }

  const channelEmoji = {
    critical: '',
    general: '',
    lessons: '',
    review: '',
    handoff: '',
  }

  const priorityStyle = priorityStyles[message.priority] || priorityStyles.normal

  return (
    <div
      className={`p-2 bg-zinc-800/50 rounded border-l-2 ${priorityStyle} transition-colors`}
      role="article"
      aria-label={`Message from ${message.from_agent} to ${message.to_agent}`}
    >
      <div className="flex justify-between items-center text-xs">
        <span className={agentColorClass}>{message.from_agent}</span>
        <span className="text-zinc-500">
          <span className="text-zinc-600 mx-1">&rarr;</span>
          {message.to_agent}
        </span>
      </div>
      <div className="text-sm mt-1 text-zinc-300 break-words">{message.body}</div>
      <div className="flex justify-between items-center text-xs text-zinc-600 mt-1">
        <span>
          {channelEmoji[message.channel]}#{message.channel}
          {message.priority !== 'normal' && (
            <span className="ml-2 text-zinc-500">({message.priority})</span>
          )}
        </span>
        <time dateTime={message.created_at}>
          {new Date(message.created_at).toLocaleTimeString()}
        </time>
      </div>
    </div>
  )
}

export default MessageBusPanel
