import { useState, useEffect } from 'react'
import { getTemplates, createTemplate, updateTemplate, deleteTemplate } from '../lib/api'
import ConfirmDialog from './ConfirmDialog'
import { useToast } from './Toast'

const emptyForm = { name: '', description: '', config: { agent_count: 4, max_phases: 24 } }

export default function TemplateManager({ onTemplatesChange }) {
  const [templates, setTemplates] = useState([])
  const [editing, setEditing] = useState(null) // null = list view, 'new' = create, id = edit
  const [form, setForm] = useState({ ...emptyForm })
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const toast = useToast()

  const refresh = async () => {
    try {
      const data = await getTemplates()
      setTemplates(data)
      onTemplatesChange?.(data)
    } catch (err) {
      toast(`Failed to load templates: ${err.message}`, 'error')
    }
  }

  useEffect(() => { refresh() }, [])

  const startCreate = () => {
    setForm({ ...emptyForm })
    setEditing('new')
  }

  const startEdit = (tmpl) => {
    setForm({
      name: tmpl.name,
      description: tmpl.description || '',
      config: tmpl.config || { agent_count: 4, max_phases: 24 },
    })
    setEditing(tmpl.id)
  }

  const cancel = () => {
    setEditing(null)
    setForm({ ...emptyForm })
  }

  const handleSave = async (e) => {
    e.preventDefault()
    if (!form.name.trim()) return
    setSaving(true)
    try {
      if (editing === 'new') {
        await createTemplate(form)
        toast('Template created', 'success')
      } else {
        await updateTemplate(editing, form)
        toast('Template updated', 'success')
      }
      setEditing(null)
      setForm({ ...emptyForm })
      await refresh()
    } catch (err) {
      toast(`Save failed: ${err.message}`, 'error', 4000, { label: 'Retry', onClick: () => handleSave(e) })
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteTemplate(deleteTarget.id)
      toast('Template deleted', 'success')
      setDeleteTarget(null)
      await refresh()
    } catch (err) {
      toast(`Delete failed: ${err.message}`, 'error', 4000, { label: 'Retry', onClick: handleDelete })
    }
  }

  const inputClass = 'retro-input w-full rounded px-3 py-2 text-sm transition-colors'
  const labelClass = 'block text-xs font-medium text-zinc-400 mb-1 font-mono uppercase tracking-wider'

  // Edit/Create form
  if (editing !== null) {
    return (
      <div className="retro-panel border border-retro-border rounded p-4 animate-fade-in">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-3 m-0 font-mono">
          {editing === 'new' ? 'New Template' : 'Edit Template'}
        </h3>
        <form onSubmit={handleSave} className="space-y-3">
          <div>
            <label className={labelClass}>Name</label>
            <input
              className={inputClass}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="Template name"
              required
              maxLength={200}
            />
          </div>
          <div>
            <label className={labelClass}>Description</label>
            <input
              className={inputClass}
              value={form.description}
              onChange={(e) => setForm((f) => ({ ...f, description: e.target.value }))}
              placeholder="Brief description..."
              maxLength={2000}
            />
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className={labelClass}>Agents</label>
              <input
                type="number"
                className={inputClass}
                value={form.config.agent_count ?? 4}
                onChange={(e) => setForm((f) => ({
                  ...f,
                  config: { ...f.config, agent_count: parseInt(e.target.value) || 4 },
                }))}
                min={1}
                max={16}
              />
            </div>
            <div>
              <label className={labelClass}>Max Phases</label>
              <input
                type="number"
                className={inputClass}
                value={form.config.max_phases ?? 24}
                onChange={(e) => setForm((f) => ({
                  ...f,
                  config: { ...f.config, max_phases: parseInt(e.target.value) || 24 },
                }))}
                min={1}
                max={24}
              />
            </div>
          </div>
          <div className="flex gap-2 pt-1">
            <button
              type="submit"
              disabled={saving || !form.name.trim()}
              className="btn-neon px-4 py-1.5 rounded text-sm disabled:opacity-50"
            >
              {saving ? 'Saving...' : 'Save'}
            </button>
            <button
              type="button"
              onClick={cancel}
              className="px-4 py-1.5 rounded bg-retro-grid text-zinc-400 hover:text-zinc-200 text-sm border border-retro-border cursor-pointer transition-colors"
            >
              Cancel
            </button>
          </div>
        </form>
      </div>
    )
  }

  // List view
  return (
    <div className="retro-panel border border-retro-border rounded p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">
          Templates
        </h3>
        <button
          onClick={startCreate}
          className="px-2.5 py-1 rounded text-xs font-mono text-crt-green hover:bg-retro-grid bg-transparent border border-crt-green/30 cursor-pointer transition-colors"
        >
          + New
        </button>
      </div>

      {templates.length === 0 && (
        <div className="text-zinc-600 text-sm text-center py-3 font-mono">
          No templates yet
        </div>
      )}

      <div className="space-y-1">
        {templates.map((tmpl) => (
          <div
            key={tmpl.id}
            className="flex items-center justify-between px-3 py-2 rounded hover:bg-retro-grid/50 transition-colors group"
          >
            <div className="min-w-0">
              <div className="text-sm text-zinc-200 font-mono truncate">{tmpl.name}</div>
              {tmpl.description && (
                <div className="text-[10px] text-zinc-600 truncate">{tmpl.description}</div>
              )}
              <div className="text-[10px] text-zinc-600 font-mono">
                {tmpl.config?.agent_count ?? '?'} agents · {tmpl.config?.max_phases ?? '?'} phases
              </div>
            </div>
            <div className="flex items-center gap-1 shrink-0 opacity-0 group-hover:opacity-100 transition-opacity">
              <button
                onClick={() => startEdit(tmpl)}
                className="p-1 rounded text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
                title="Edit template"
                aria-label={`Edit ${tmpl.name}`}
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M11 2l3 3L5 14H2v-3L11 2z" />
                </svg>
              </button>
              <button
                onClick={() => setDeleteTarget(tmpl)}
                className="p-1 rounded text-zinc-500 hover:text-signal-red hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
                title="Delete template"
                aria-label={`Delete ${tmpl.name}`}
              >
                <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                  <path d="M2 4h12M5.33 4V2.67a1.33 1.33 0 011.34-1.34h2.66a1.33 1.33 0 011.34 1.34V4" />
                  <path d="M3.33 4l.67 9.33a1.33 1.33 0 001.33 1.34h5.34a1.33 1.33 0 001.33-1.34L12.67 4" />
                </svg>
              </button>
            </div>
          </div>
        ))}
      </div>

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Template"
        message={deleteTarget ? `Delete template "${deleteTarget.name}"?` : ''}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
