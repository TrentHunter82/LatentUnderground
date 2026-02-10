import { useEffect, useRef, useCallback } from 'react'
import { KEYBOARD_SHORTCUTS } from '../lib/constants'

export default function ShortcutCheatsheet({ open, onClose }) {
  const dialogRef = useRef(null)
  const closeButtonRef = useRef(null)

  useEffect(() => {
    if (open) {
      closeButtonRef.current?.focus()
    }
  }, [open])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      onClose()
      return
    }

    if (e.key === 'Tab') {
      const dialog = dialogRef.current
      if (!dialog) return

      const focusable = dialog.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
      )
      if (focusable.length === 0) return

      const first = focusable[0]
      const last = focusable[focusable.length - 1]

      if (e.shiftKey) {
        if (document.activeElement === first) {
          e.preventDefault()
          last.focus()
        }
      } else {
        if (document.activeElement === last) {
          e.preventDefault()
          first.focus()
        }
      }
    }
  }, [onClose])

  if (!open) return null

  const groupedShortcuts = KEYBOARD_SHORTCUTS.reduce((acc, shortcut) => {
    if (!acc[shortcut.group]) acc[shortcut.group] = []
    acc[shortcut.group].push(shortcut)
    return acc
  }, {})

  const renderKeys = (keys) => {
    const parts = keys.split('+')
    return (
      <span className="inline-flex gap-1 items-center">
        {parts.map((key, idx) => (
          <kbd
            key={idx}
            className="bg-retro-dark border border-retro-border rounded px-1.5 py-0.5 font-mono text-xs text-crt-green"
          >
            {key}
          </kbd>
        ))}
      </span>
    )
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onClose}>
      <div className="absolute inset-0 bg-black/70" />

      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="shortcuts-dialog-title"
        className="relative retro-panel border border-retro-border rounded shadow-2xl max-w-2xl w-full mx-4 p-6 glow-green"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <h3 id="shortcuts-dialog-title" className="text-lg font-semibold text-zinc-100 m-0 mb-6 font-mono">
          Keyboard Shortcuts
        </h3>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
          {Object.entries(groupedShortcuts).map(([group, shortcuts]) => (
            <div key={group} className="space-y-3">
              <h4 className="text-sm font-semibold text-crt-cyan uppercase tracking-wider font-mono m-0">
                {group}
              </h4>
              <div className="space-y-2">
                {shortcuts.map((shortcut, idx) => (
                  <div key={idx} className="flex items-center justify-between gap-4 py-1">
                    <span className="text-sm text-zinc-300">{shortcut.description}</span>
                    {renderKeys(shortcut.keys)}
                  </div>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="flex justify-end">
          <button
            ref={closeButtonRef}
            onClick={onClose}
            className="btn-neon px-4 py-2 rounded text-sm font-medium cursor-pointer font-mono"
            aria-label="Close keyboard shortcuts dialog"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  )
}
