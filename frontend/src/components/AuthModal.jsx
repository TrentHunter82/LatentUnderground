import { useState, useEffect, useRef, useCallback } from 'react'
import { setApiKey, getStoredApiKey, clearApiKey } from '../lib/api'

export default function AuthModal({ open, onClose }) {
  const [key, setKey] = useState('')
  const inputRef = useRef(null)
  const dialogRef = useRef(null)

  useEffect(() => {
    if (open) {
      setKey(getStoredApiKey() || '')
      setTimeout(() => inputRef.current?.focus(), 50)
    }
  }, [open])

  const handleSave = () => {
    setApiKey(key.trim())
    onClose()
  }

  const handleClear = () => {
    clearApiKey()
    setKey('')
    onClose()
  }

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      onClose()
      return
    }
    if (e.key === 'Enter') {
      handleSave()
      return
    }
    if (e.key === 'Tab') {
      const dialog = dialogRef.current
      if (!dialog) return
      const focusable = dialog.querySelectorAll(
        'button, input, [tabindex]:not([tabindex="-1"])'
      )
      if (focusable.length === 0) return
      const first = focusable[0]
      const last = focusable[focusable.length - 1]
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault()
        last.focus()
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault()
        first.focus()
      }
    }
  }, [onClose])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70" />
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="auth-dialog-title"
        className="relative retro-panel border border-retro-border rounded shadow-2xl max-w-md w-full mx-4 p-6 glow-green"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <h3 id="auth-dialog-title" className="text-lg font-semibold text-zinc-100 m-0 font-mono">API Key</h3>
        <p className="text-sm text-zinc-400 mt-2 mb-4">
          Enter your API key to authenticate. Leave empty to disable authentication.
        </p>

        <input
          ref={inputRef}
          type="password"
          value={key}
          onChange={(e) => setKey(e.target.value)}
          placeholder="Enter API key..."
          className="retro-input w-full px-3 py-2 text-sm font-mono mb-4"
          aria-label="API key"
        />

        <div className="flex justify-between">
          <button
            onClick={handleClear}
            className="px-3 py-2 rounded text-xs font-mono text-zinc-500 hover:text-signal-red bg-transparent border border-retro-border cursor-pointer transition-colors"
          >
            Clear Key
          </button>
          <div className="flex gap-3">
            <button
              onClick={onClose}
              className="px-4 py-2 rounded text-sm font-medium text-zinc-300 bg-retro-grid hover:bg-retro-border border border-retro-border cursor-pointer transition-colors font-mono"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              className="btn-neon px-4 py-2 rounded text-sm font-medium cursor-pointer font-mono"
            >
              Save
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
