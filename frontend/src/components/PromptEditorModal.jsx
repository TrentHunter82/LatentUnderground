import { useState, useEffect, useRef } from 'react'
import { updateAgentPrompt, restartAgent } from '../lib/api'
import { useToast } from './Toast'
import { AGENT_NEON_COLORS } from '../lib/constants'

export default function PromptEditorModal({ open, projectId, agentName, currentPrompt, onClose, onSaved }) {
  const [content, setContent] = useState(currentPrompt || '')
  const [saving, setSaving] = useState(false)
  const [originalContent] = useState(currentPrompt || '')
  const textareaRef = useRef(null)
  const toast = useToast()

  useEffect(() => {
    if (open) {
      setContent(currentPrompt || '')
      setTimeout(() => textareaRef.current?.focus(), 100)
    }
  }, [open, currentPrompt])

  if (!open) return null

  const hasChanges = content !== originalContent

  const handleSave = async (andRestart = false) => {
    if (!content.trim()) {
      toast('Prompt cannot be empty', 'error')
      return
    }

    setSaving(true)
    try {
      await updateAgentPrompt(projectId, agentName, content)
      toast(`Prompt saved for ${agentName}`, 'success')

      if (andRestart) {
        try {
          await restartAgent(projectId, agentName)
          toast(`${agentName} restarted with new prompt`, 'success')
        } catch (e) {
          toast(`Prompt saved but restart failed: ${e.message}`, 'error')
        }
      }

      onSaved?.()
      onClose()
    } catch (e) {
      toast(`Failed to save prompt: ${e.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.preventDefault()
      if (hasChanges && !confirm('Discard unsaved changes?')) return
      onClose()
    }
    if (e.key === 's' && (e.ctrlKey || e.metaKey)) {
      e.preventDefault()
      handleSave(false)
    }
  }

  const agentColor = AGENT_NEON_COLORS[agentName] || 'text-zinc-200'

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70"
      onClick={(e) => {
        if (e.target === e.currentTarget) {
          if (hasChanges && !confirm('Discard unsaved changes?')) return
          onClose()
        }
      }}
      role="dialog"
      aria-modal="true"
      aria-label={`Edit prompt for ${agentName}`}
    >
      <div className="retro-panel border border-retro-border rounded-lg w-full max-w-2xl max-h-[85vh] flex flex-col animate-fade-in" onKeyDown={handleKeyDown}>
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-retro-border">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-mono font-medium m-0 text-zinc-200">Edit Prompt</h2>
            <span className={`text-xs font-mono ${agentColor}`}>{agentName}</span>
          </div>
          <button
            onClick={onClose}
            className="text-zinc-500 hover:text-zinc-300 bg-transparent border-0 cursor-pointer p-1"
            aria-label="Close prompt editor"
          >
            <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M11 3L3 11M3 3l8 8" />
            </svg>
          </button>
        </div>

        {/* Editor */}
        <div className="flex-1 p-4 overflow-hidden flex flex-col min-h-0">
          <textarea
            ref={textareaRef}
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="retro-input flex-1 w-full px-3 py-2 text-xs font-mono resize-none rounded min-h-[200px]"
            aria-label={`Prompt content for ${agentName}`}
            aria-describedby={`prompt-shortcuts-${agentName}`}
            disabled={saving}
            spellCheck={false}
          />
          <span id={`prompt-shortcuts-${agentName}`} className="sr-only">Press Ctrl+S to save, Escape to close</span>
          <div className="flex items-center justify-between mt-2 text-[10px] text-zinc-600 font-mono">
            <span>{content.length} characters</span>
            {hasChanges && <span className="text-crt-amber" aria-live="polite">Unsaved changes</span>}
          </div>
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-retro-border">
          <button
            onClick={onClose}
            className="px-3 py-1.5 rounded text-xs font-mono text-zinc-400 hover:text-zinc-200 bg-transparent border border-retro-border cursor-pointer transition-colors"
            disabled={saving}
          >
            Cancel
          </button>
          <button
            onClick={() => handleSave(false)}
            disabled={saving || !hasChanges}
            className="btn-neon px-3 py-1.5 rounded text-xs disabled:opacity-30 flex items-center gap-1.5"
            aria-busy={saving}
          >
            {saving ? 'Saving...' : 'Save'}
          </button>
          <button
            onClick={() => handleSave(true)}
            disabled={saving || !hasChanges}
            className="btn-neon px-3 py-1.5 rounded text-xs disabled:opacity-30 flex items-center gap-1.5"
            aria-busy={saving}
            title="Save prompt and restart the agent"
          >
            {saving ? 'Saving...' : 'Save & Restart'}
          </button>
        </div>
      </div>
    </div>
  )
}
