import { useState } from 'react'
import { useSendBusMessage } from '../hooks/useMutations'
import { AGENT_NAMES } from '../lib/constants'

/**
 * Message composer for sending messages to agents via the message bus.
 * Supports target selection, channel, priority, and message body.
 */
export default function MessageComposer({ projectId, onSend }) {
  const [form, setForm] = useState({
    to_agent: 'all',
    channel: 'general',
    priority: 'normal',
    body: '',
  })
  const [error, setError] = useState(null)

  const sendMutation = useSendBusMessage({
    onSuccess: () => {
      setForm((f) => ({ ...f, body: '' }))
      setError(null)
      onSend?.()
    },
    onError: (err) => {
      setError(err.message || 'Failed to send message')
    },
  })

  const handleSubmit = (e) => {
    e.preventDefault()
    if (!form.body.trim()) return

    sendMutation.mutate({
      projectId,
      data: {
        from_agent: 'human',
        to_agent: form.to_agent,
        channel: form.channel,
        priority: form.priority,
        msg_type: 'request',
        body: form.body.trim(),
      },
    })
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSubmit(e)
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      <div className="flex gap-2 flex-wrap">
        <select
          className="retro-input text-xs py-1.5 px-2"
          value={form.to_agent}
          onChange={(e) => setForm((f) => ({ ...f, to_agent: e.target.value }))}
          aria-label="Send to"
        >
          <option value="all">Broadcast All</option>
          {AGENT_NAMES.filter((n) => n !== 'supervisor').map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
        </select>

        <select
          className="retro-input text-xs py-1.5 px-2"
          value={form.channel}
          onChange={(e) => setForm((f) => ({ ...f, channel: e.target.value }))}
          aria-label="Channel"
        >
          <option value="general">General</option>
          <option value="critical">Critical</option>
          <option value="review">Review</option>
          <option value="handoff">Handoff</option>
        </select>

        <select
          className="retro-input text-xs py-1.5 px-2"
          value={form.priority}
          onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value }))}
          aria-label="Priority"
        >
          <option value="normal">Normal</option>
          <option value="high">High</option>
          <option value="critical">Critical</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div className="flex gap-2">
        <input
          type="text"
          className="retro-input flex-1 text-sm py-1.5 px-3"
          placeholder="Type a message..."
          value={form.body}
          onChange={(e) => setForm((f) => ({ ...f, body: e.target.value }))}
          onKeyDown={handleKeyDown}
          aria-label="Message body"
          maxLength={1000}
        />
        <button
          type="submit"
          disabled={sendMutation.isPending || !form.body.trim()}
          className="btn-neon px-4 py-1.5 text-sm disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {sendMutation.isPending ? 'Sending...' : 'Send'}
        </button>
      </div>

      {error && (
        <div className="text-signal-red text-xs" role="alert">
          {error}
        </div>
      )}
    </form>
  )
}
