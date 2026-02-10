import { useState, useEffect, useCallback, useRef } from 'react'
import { browseDirectory } from '../lib/api'
import { useSafeToast } from './Toast'

export default function FolderBrowser({ open, onSelect, onClose }) {
  const toast = useSafeToast()
  const [currentPath, setCurrentPath] = useState('')
  const [parentPath, setParentPath] = useState(null)
  const [dirs, setDirs] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [newFolderName, setNewFolderName] = useState('')
  const dialogRef = useRef(null)

  const browse = useCallback(async (path = '') => {
    setLoading(true)
    setError(null)
    try {
      const data = await browseDirectory(path)
      setCurrentPath(data.path || '')
      setParentPath(data.parent)
      setDirs(data.dirs || [])
    } catch (e) {
      setError(e.message)
      toast(`Browse failed: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: () => browse(path) })
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (open) {
      browse('')
      const timer = setTimeout(() => dialogRef.current?.focus(), 50)
      return () => clearTimeout(timer)
    }
  }, [open, browse])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      onClose()
      return
    }
    if (e.key === 'Tab') {
      const dialog = dialogRef.current
      if (!dialog) return
      const focusable = dialog.querySelectorAll(
        'button:not([disabled]), input, [tabindex]:not([tabindex="-1"])'
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

  const handleSelect = () => {
    if (!currentPath) return
    // If user typed a new folder name, append it
    const finalPath = newFolderName
      ? `${currentPath}${currentPath.endsWith('\\') || currentPath.endsWith('/') ? '' : '/'}${newFolderName}`
      : currentPath
    onSelect(finalPath)
    onClose()
  }

  if (!open) return null

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm" onClick={onClose}>
      <div
        ref={dialogRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby="folder-browser-title"
        className="retro-panel w-full max-w-lg mx-4 rounded-lg shadow-2xl border border-retro-border overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
      >
        {/* Header */}
        <div className="flex items-center justify-between px-4 py-3 border-b border-retro-border">
          <h2 id="folder-browser-title" className="text-sm font-mono font-semibold text-zinc-200 uppercase tracking-wider">
            Browse for Folder
          </h2>
          <button
            onClick={onClose}
            className="p-1 text-zinc-500 hover:text-zinc-300 bg-transparent border-0 cursor-pointer"
            aria-label="Close"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M4 4l8 8M12 4l-8 8" />
            </svg>
          </button>
        </div>

        {/* Current path bar */}
        <div className="px-4 py-2 border-b border-retro-border flex items-center gap-2">
          <button
            onClick={() => parentPath !== null && browse(parentPath)}
            disabled={parentPath === null || loading}
            className="p-1.5 rounded text-zinc-400 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer disabled:opacity-30 disabled:cursor-default transition-colors shrink-0"
            title="Go up"
            aria-label="Go to parent directory"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M8 12V4M4 8l4-4 4 4" />
            </svg>
          </button>
          <div className="flex-1 px-2 py-1 bg-retro-grid rounded text-xs font-mono text-zinc-300 truncate border border-retro-border">
            {currentPath || 'My Computer'}
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="px-4 py-2 text-xs font-mono text-signal-red bg-signal-red/10">
            {error}
          </div>
        )}

        {/* Directory list */}
        <div className="h-64 overflow-y-auto px-2 py-1">
          {loading ? (
            <div className="flex items-center justify-center h-full text-zinc-500 text-sm font-mono">
              Loading...
            </div>
          ) : dirs.length === 0 ? (
            <div className="flex items-center justify-center h-full text-zinc-600 text-sm font-mono">
              No subdirectories
            </div>
          ) : (
            dirs.map((dir) => (
              <button
                key={dir.path}
                onClick={() => browse(dir.path)}
                aria-label={`Open folder ${dir.name}`}
                className="flex items-center gap-2 w-full px-3 py-1.5 rounded text-left text-sm font-mono text-zinc-300 hover:bg-retro-grid hover:text-crt-green bg-transparent border-0 cursor-pointer transition-colors"
              >
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor" className="text-crt-amber shrink-0" opacity="0.7">
                  <path d="M1 3.5A1.5 1.5 0 012.5 2h3.379a1.5 1.5 0 011.06.44L8.062 3.56A1.5 1.5 0 009.122 4H13.5A1.5 1.5 0 0115 5.5v7a1.5 1.5 0 01-1.5 1.5h-11A1.5 1.5 0 011 12.5v-9z" />
                </svg>
                <span className="truncate">{dir.name}</span>
              </button>
            ))
          )}
        </div>

        {/* Subfolder name input */}
        <div className="px-4 py-2 border-t border-retro-border">
          <label className="block text-[10px] font-mono text-zinc-500 uppercase tracking-wider mb-1">
            Subfolder name (optional, will be appended to path)
          </label>
          <input
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="my-new-project"
            className="retro-input w-full rounded px-3 py-1.5 text-sm"
            aria-label="Subfolder name to append to selected path"
          />
        </div>

        {/* Footer */}
        <div className="flex items-center justify-end gap-2 px-4 py-3 border-t border-retro-border">
          <button
            onClick={onClose}
            className="px-4 py-2 rounded bg-retro-grid hover:bg-retro-border text-zinc-400 text-sm font-mono border border-retro-border cursor-pointer transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSelect}
            disabled={!currentPath}
            className="btn-neon px-4 py-2 rounded text-sm disabled:opacity-50"
          >
            Select Folder
          </button>
        </div>
      </div>
    </div>
  )
}
