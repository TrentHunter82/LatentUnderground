import { useState, useEffect, useCallback, useRef } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { getFile, putFile } from '../lib/api'
import { useToast } from './Toast'

const editableFiles = [
  { path: 'tasks/TASKS.md', label: 'Tasks' },
  { path: 'tasks/lessons.md', label: 'Lessons' },
  { path: 'tasks/todo.md', label: 'Plans' },
]

export default function FileEditor({ projectId, wsEvents }) {
  const [activeFile, setActiveFile] = useState(editableFiles[0].path)
  const [content, setContent] = useState('')
  const [original, setOriginal] = useState('')
  const [editing, setEditing] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState(null)
  const [lastModified, setLastModified] = useState(null)
  const [rehypePlugin, setRehypePlugin] = useState(null)
  const toast = useToast()

  // Lazy-load rehype-highlight (pulls in highlight.js ~179KB) on first render
  const loadedRef = useRef(false)
  useEffect(() => {
    if (loadedRef.current) return
    loadedRef.current = true
    import('rehype-highlight').then((mod) => {
      setRehypePlugin(() => mod.default)
    }).catch(() => {})
  }, [])

  const loadFile = useCallback(async () => {
    try {
      const data = await getFile(activeFile, projectId)
      setContent(data.content)
      setOriginal(data.content)
      setLastModified(new Date().toLocaleTimeString())
      setError(null)
    } catch (e) {
      setContent('')
      setOriginal('')
      setLastModified(null)
      // 404 = file not created yet (normal during swarm startup) — no toast
      if (e.message?.includes('404')) {
        setError(null)
      } else {
        setError(e.message)
        toast(`Failed to load file: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: loadFile })
      }
    }
  }, [activeFile, projectId])

  useEffect(() => {
    loadFile()
    setEditing(false)
  }, [loadFile])

  // Auto-reload on file_changed events
  useEffect(() => {
    if (wsEvents?.type === 'file_changed' && !editing) {
      const changed = wsEvents.file
      if (changed === activeFile || changed.endsWith(activeFile.split('/').pop())) {
        loadFile()
      }
    }
  }, [wsEvents, activeFile, editing, loadFile])

  const handleSave = useCallback(async () => {
    if (content === original) return
    setSaving(true)
    try {
      await putFile(activeFile, content, projectId)
      setOriginal(content)
      setEditing(false)
      setError(null)
      setLastModified(new Date().toLocaleTimeString())
      toast('File saved', 'success', 2000)
    } catch (e) {
      setError(e.message)
      toast(`Save failed: ${e.message}`, 'error', 4000, { label: 'Retry', onClick: handleSave })
    } finally {
      setSaving(false)
    }
  }, [activeFile, content, original, projectId, toast])

  const handleCancel = useCallback(() => {
    setContent(original)
    setEditing(false)
  }, [original])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKey = (e) => {
      if (e.key === 's' && (e.ctrlKey || e.metaKey) && editing) {
        e.preventDefault()
        handleSave()
      }
      if (e.key === 'Escape' && editing) {
        handleCancel()
      }
    }
    window.addEventListener('keydown', handleKey)
    return () => window.removeEventListener('keydown', handleKey)
  }, [editing, handleSave, handleCancel])

  const hasChanges = content !== original

  const tabRefs = useRef({})

  const handleTabKeyDown = useCallback((e) => {
    const idx = editableFiles.findIndex((f) => f.path === activeFile)
    let next = -1

    if (e.key === 'ArrowRight') next = (idx + 1) % editableFiles.length
    else if (e.key === 'ArrowLeft') next = (idx - 1 + editableFiles.length) % editableFiles.length
    else if (e.key === 'Home') next = 0
    else if (e.key === 'End') next = editableFiles.length - 1
    else return

    e.preventDefault()
    const nextPath = editableFiles[next].path
    setActiveFile(nextPath)
    tabRefs.current[nextPath]?.focus()
  }, [activeFile])

  return (
    <div className="retro-panel border border-retro-border rounded flex flex-col h-full">
      {/* File tabs */}
      <div className="flex items-center gap-1 px-3 py-2 border-b border-retro-border">
        <div role="tablist" aria-label="File tabs" className="flex items-center gap-1">
          {editableFiles.map((f) => (
            <button
              key={f.path}
              ref={(el) => { tabRefs.current[f.path] = el }}
              onClick={() => setActiveFile(f.path)}
              onKeyDown={handleTabKeyDown}
              role="tab"
              aria-selected={activeFile === f.path}
              aria-controls="file-editor-panel"
              tabIndex={activeFile === f.path ? 0 : -1}
              aria-label={`${f.label} file`}
              className={`px-2 sm:px-3 py-1 sm:py-1.5 rounded text-xs font-medium transition-colors cursor-pointer border-0 font-mono ${
                activeFile === f.path
                  ? 'bg-retro-grid text-crt-green border border-crt-green/30'
                  : 'text-zinc-500 hover:text-zinc-300 bg-transparent'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>

        <div className="flex-1" />

        {/* Last modified timestamp */}
        {lastModified && (
          <span className="text-[10px] text-zinc-600 mr-2 font-mono">
            Updated {lastModified}
          </span>
        )}

        {editing ? (
          <div className="flex gap-2">
            <button
              onClick={handleCancel}
              className="px-3 py-1.5 rounded text-xs text-zinc-400 hover:text-zinc-200 bg-transparent border-0 cursor-pointer font-mono"
              title="Escape"
            >
              Cancel
            </button>
            <button
              onClick={handleSave}
              disabled={saving || !hasChanges}
              className="btn-neon px-3 py-1.5 rounded text-xs disabled:opacity-50"
              title="Ctrl+S"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
          </div>
        ) : (
          <button
            onClick={() => setEditing(true)}
            className="px-3 py-1.5 rounded text-xs text-zinc-400 hover:text-crt-green bg-transparent border-0 cursor-pointer font-mono"
          >
            Edit
          </button>
        )}
      </div>

      {error && (
        <div className="px-4 py-2 bg-signal-red/10 border-b border-signal-red/20 text-signal-red text-xs font-mono">
          {error}
        </div>
      )}

      {/* Content */}
      <div id="file-editor-panel" role="tabpanel" className="flex-1 overflow-y-auto p-4">
        {editing ? (
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            className="retro-input w-full h-full min-h-64 rounded p-3 text-sm resize-y"
            spellCheck={false}
            aria-label={`Edit ${editableFiles.find(f => f.path === activeFile)?.label || 'file'} content`}
          />
        ) : (
          <div className="markdown-body text-sm text-zinc-300">
            <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={rehypePlugin ? [rehypePlugin] : []}>{content || '*File not created yet — it will appear once the swarm generates it.*'}</ReactMarkdown>
          </div>
        )}
      </div>
    </div>
  )
}
