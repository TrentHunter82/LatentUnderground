import { useEffect, useRef, useCallback } from 'react'

export default function ConfirmDialog({ open, title, message, confirmLabel = 'Confirm', cancelLabel = 'Cancel', danger = false, onConfirm, onCancel }) {
  const dialogRef = useRef(null)
  const confirmRef = useRef(null)

  useEffect(() => {
    if (open) confirmRef.current?.focus()
  }, [open])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      onCancel?.()
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
  }, [onCancel])

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" onClick={onCancel}>
      {/* Backdrop */}
      <div className="absolute inset-0 bg-black/70" />

      {/* Dialog */}
      <div
        ref={dialogRef}
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="confirm-dialog-title"
        aria-describedby="confirm-dialog-message"
        className="relative retro-panel border border-retro-border rounded shadow-2xl max-w-md w-full mx-4 p-6 glow-green"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        <h3 id="confirm-dialog-title" className="text-lg font-semibold text-zinc-100 m-0 font-mono">{title}</h3>
        <p id="confirm-dialog-message" className="text-sm text-zinc-400 mt-2 mb-5">{message}</p>

        <div className="flex justify-end gap-3">
          <button
            onClick={onCancel}
            className="px-4 py-2 rounded text-sm font-medium text-zinc-300 bg-retro-grid hover:bg-retro-border border border-retro-border cursor-pointer transition-colors font-mono"
          >
            {cancelLabel}
          </button>
          <button
            ref={confirmRef}
            onClick={onConfirm}
            className={`px-4 py-2 rounded text-sm font-medium border cursor-pointer transition-colors font-mono ${
              danger
                ? 'btn-neon-danger'
                : 'btn-neon'
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  )
}
