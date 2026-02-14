import { useState, useEffect, useRef, useCallback } from 'react'
import { sendDirective, getDirectiveStatus } from '../lib/api'
import { useToast } from './Toast'

export default function DirectivePanel({ projectId, agentName, onClose }) {
  const [text, setText] = useState('')
  const [priority, setPriority] = useState('normal')
  const [sending, setSending] = useState(false)
  const [pending, setPending] = useState(false)
  const [pendingText, setPendingText] = useState(null)
  const textareaRef = useRef(null)
  const toast = useToast()
  const pollRef = useRef(null)

  // Check for pending directive on mount and poll
  const checkPending = useCallback(async () => {
    if (!projectId || !agentName) return
    try {
      const data = await getDirectiveStatus(projectId, agentName)
      setPending(data.pending || false)
      setPendingText(data.pending ? data.text : null)
    } catch {
      // Endpoint may not exist yet
      setPending(false)
    }
  }, [projectId, agentName])

  useEffect(() => {
    checkPending()
    pollRef.current = setInterval(checkPending, 3000)
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [checkPending])

  useEffect(() => {
    textareaRef.current?.focus()
  }, [])

  const handleSend = async () => {
    const trimmed = text.trim()
    if (!trimmed) return
    if (trimmed.length > 5000) {
      toast('Directive must be 5000 characters or less', 'error')
      return
    }

    setSending(true)
    try {
      await sendDirective(projectId, agentName, trimmed, priority)
      toast(`Directive sent to ${agentName}`, 'success')
      setText('')
      setPending(true)
      setPendingText(trimmed)
    } catch (e) {
      toast(`Failed to send directive: ${e.message}`, 'error')
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSend()
    } else if (e.key === 'Escape') {
      e.preventDefault()
      onClose?.()
    }
  }

  return (
    <div className="retro-panel border border-retro-border rounded p-3 animate-fade-in">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-2">
          <h3 className="text-[10px] uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">
            Direct {agentName}
          </h3>
          {pending && (
            <span className="flex items-center gap-1 text-[10px] text-crt-amber font-mono" role="status">
              <span className="w-1.5 h-1.5 rounded-full bg-crt-amber animate-pulse" role="img" aria-label="Directive pending" />
              Pending
            </span>
          )}
        </div>
        {onClose && (
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 bg-transparent border-0 cursor-pointer text-xs p-1"
            aria-label="Close directive panel"
          >
            ✕
          </button>
        )}
      </div>

      {pending && pendingText && (
        <div className="text-[10px] text-zinc-600 font-mono bg-retro-grid/30 rounded px-2 py-1.5 mb-2 line-clamp-2">
          Queued: {pendingText}
        </div>
      )}

      <textarea
        ref={textareaRef}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={`Enter directive for ${agentName}... (Ctrl+Enter to send)`}
        rows={3}
        maxLength={5000}
        className="retro-input w-full px-2 py-1.5 text-[11px] font-mono resize-y min-h-[60px] rounded"
        aria-label={`Directive text for ${agentName}`}
        disabled={sending}
      />

      <div className="flex items-center justify-between mt-2">
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer">
            <input
              type="radio"
              name={`priority-${agentName}`}
              value="normal"
              checked={priority === 'normal'}
              onChange={() => setPriority('normal')}
              className="accent-crt-green w-3 h-3"
            />
            <span className="text-[10px] text-zinc-500 font-mono">Normal</span>
          </label>
          <label className="flex items-center gap-1.5 cursor-pointer" title="Urgent: stops and restarts the agent with the directive">
            <input
              type="radio"
              name={`priority-${agentName}`}
              value="urgent"
              checked={priority === 'urgent'}
              onChange={() => setPriority('urgent')}
              className="accent-signal-red w-3 h-3"
              aria-describedby={`urgent-desc-${agentName}`}
            />
            <span className="text-[10px] text-signal-red font-mono">Urgent</span>
            <span id={`urgent-desc-${agentName}`} className="sr-only">Stops and restarts the agent with the directive</span>
          </label>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-[9px] text-zinc-700 font-mono">{text.length}/5000</span>
          <button
            onClick={handleSend}
            disabled={sending || !text.trim()}
            className="btn-neon px-3 py-1 rounded text-[11px] disabled:opacity-30 flex items-center gap-1.5"
            aria-busy={sending}
          >
            {sending ? (
              <>
                <span className="inline-block w-3 h-3 border-2 border-current/30 border-t-current rounded-full animate-spin" aria-hidden="true" />
                Sending...
              </>
            ) : (
              'Send'
            )}
          </button>
        </div>
      </div>
    </div>
  )
}
