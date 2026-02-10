import { useState, useEffect, useCallback, useRef } from 'react'
import { getWebhooks, createWebhook, updateWebhook, deleteWebhook } from '../lib/api'
import ConfirmDialog from './ConfirmDialog'
import { useToast } from './Toast'

const WEBHOOK_EVENTS = ['swarm_launched', 'swarm_stopped', 'swarm_crashed', 'swarm_error']

const emptyForm = { url: '', events: [], secret: '' }

export default function WebhookManager({ projectId }) {
  const [webhooks, setWebhooks] = useState([])
  const [loading, setLoading] = useState(true)
  const [showForm, setShowForm] = useState(false)
  const [form, setForm] = useState({ ...emptyForm })
  const [saving, setSaving] = useState(false)
  const [editingId, setEditingId] = useState(null)
  const [deleteTarget, setDeleteTarget] = useState(null)
  const toast = useToast()
  const mountedRef = useRef(true)

  useEffect(() => {
    mountedRef.current = true
    return () => { mountedRef.current = false }
  }, [])

  const refresh = useCallback(async () => {
    try {
      const data = await getWebhooks()
      if (!mountedRef.current) return
      const filtered = data.filter(
        (wh) => wh.project_id === projectId || wh.project_id === null
      )
      setWebhooks(filtered)
    } catch (err) {
      if (!mountedRef.current) return
      toast(`Failed to load webhooks: ${err.message}`, 'error')
    } finally {
      if (mountedRef.current) setLoading(false)
    }
  }, [projectId, toast])

  useEffect(() => {
    refresh()
  }, [refresh])

  const toggleEvent = (event) => {
    setForm((f) => ({
      ...f,
      events: f.events.includes(event)
        ? f.events.filter((e) => e !== event)
        : [...f.events, event],
    }))
  }

  const startCreate = () => {
    setForm({ ...emptyForm })
    setEditingId(null)
    setShowForm(true)
  }

  const startEdit = (wh) => {
    setForm({
      url: wh.url,
      events: [...wh.events],
      secret: '',
    })
    setEditingId(wh.id)
    setShowForm(true)
  }

  const cancelForm = () => {
    setShowForm(false)
    setEditingId(null)
    setForm({ ...emptyForm })
  }

  const handleSubmit = async (e) => {
    e.preventDefault()
    if (!form.url.trim() || form.events.length === 0) return
    setSaving(true)
    try {
      if (editingId) {
        const payload = { url: form.url, events: form.events }
        if (form.secret) payload.secret = form.secret
        await updateWebhook(editingId, payload)
        toast('Webhook updated', 'success')
      } else {
        const payload = { url: form.url, events: form.events, project_id: projectId }
        if (form.secret) payload.secret = form.secret
        await createWebhook(payload)
        toast('Webhook created', 'success')
      }
      cancelForm()
      await refresh()
    } catch (err) {
      toast(`Save failed: ${err.message}`, 'error')
    } finally {
      setSaving(false)
    }
  }

  const handleToggleEnabled = async (wh) => {
    try {
      await updateWebhook(wh.id, { enabled: !wh.enabled })
      await refresh()
    } catch (err) {
      toast(`Toggle failed: ${err.message}`, 'error')
    }
  }

  const handleDelete = async () => {
    if (!deleteTarget) return
    try {
      await deleteWebhook(deleteTarget.id)
      toast('Webhook deleted', 'success')
      setDeleteTarget(null)
      await refresh()
    } catch (err) {
      toast(`Delete failed: ${err.message}`, 'error')
    }
  }

  const inputClass = 'retro-input w-full rounded px-3 py-2 text-sm transition-colors'
  const labelClass = 'block text-xs font-medium text-zinc-400 mb-1 font-mono uppercase tracking-wider'

  return (
    <div className="retro-panel retro-panel-glow rounded p-4">
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium m-0 font-mono">
          Webhooks
        </h3>
        {!showForm && (
          <button
            onClick={startCreate}
            className="px-2.5 py-1 rounded text-xs font-mono text-crt-green hover:bg-retro-grid bg-transparent border border-crt-green/30 cursor-pointer transition-colors"
            aria-label="Add new webhook"
          >
            + New
          </button>
        )}
      </div>

      {/* Create / Edit form */}
      {showForm && (
        <div className="retro-panel border border-retro-border rounded p-3 mb-3 animate-fade-in">
          <h4 className="text-xs uppercase tracking-[0.2em] text-zinc-500 font-medium mb-2 m-0 font-mono">
            {editingId ? 'Edit Webhook' : 'New Webhook'}
          </h4>
          <form onSubmit={handleSubmit} className="space-y-3">
            <div>
              <label className={labelClass} htmlFor="webhook-url">URL</label>
              <input
                id="webhook-url"
                type="url"
                className={inputClass}
                value={form.url}
                onChange={(e) => setForm((f) => ({ ...f, url: e.target.value }))}
                placeholder="https://example.com/webhook"
                required
                maxLength={2000}
              />
            </div>

            <div>
              <label className={labelClass}>Events</label>
              <div className="flex flex-wrap gap-2">
                {WEBHOOK_EVENTS.map((event) => (
                  <button
                    key={event}
                    type="button"
                    onClick={() => toggleEvent(event)}
                    className={`px-2.5 py-1 rounded text-xs font-mono border cursor-pointer transition-colors ${
                      form.events.includes(event)
                        ? 'bg-crt-green/15 text-crt-green border-crt-green/40'
                        : 'bg-retro-grid text-zinc-500 border-retro-border hover:text-zinc-300'
                    }`}
                    aria-pressed={form.events.includes(event)}
                    aria-label={`Toggle ${event} event`}
                  >
                    {event}
                  </button>
                ))}
              </div>
              {form.events.length === 0 && (
                <p className="text-[10px] text-signal-red mt-1 m-0 font-mono">
                  Select at least one event
                </p>
              )}
            </div>

            <div>
              <label className={labelClass} htmlFor="webhook-secret">
                Secret {editingId && <span className="normal-case tracking-normal text-zinc-600">(leave blank to keep current)</span>}
              </label>
              <input
                id="webhook-secret"
                type="password"
                className={inputClass}
                value={form.secret}
                onChange={(e) => setForm((f) => ({ ...f, secret: e.target.value }))}
                placeholder={editingId ? 'Leave blank to keep existing' : 'Optional HMAC secret'}
                maxLength={500}
                autoComplete="off"
              />
            </div>

            <div className="flex gap-2 pt-1">
              <button
                type="submit"
                disabled={saving || !form.url.trim() || form.events.length === 0}
                className="btn-neon px-4 py-1.5 rounded text-sm disabled:opacity-50"
              >
                {saving ? 'Saving...' : editingId ? 'Update' : 'Create'}
              </button>
              <button
                type="button"
                onClick={cancelForm}
                className="px-4 py-1.5 rounded bg-retro-grid text-zinc-400 hover:text-zinc-200 text-sm border border-retro-border cursor-pointer transition-colors"
              >
                Cancel
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Loading state */}
      {loading && (
        <div className="text-zinc-600 text-sm text-center py-3 font-mono">
          Loading webhooks...
        </div>
      )}

      {/* Empty state */}
      {!loading && webhooks.length === 0 && (
        <div className="text-zinc-600 text-sm text-center py-3 font-mono">
          No webhooks configured
        </div>
      )}

      {/* Webhook list */}
      {!loading && webhooks.length > 0 && (
        <div className="space-y-1">
          {webhooks.map((wh) => (
            <div
              key={wh.id}
              className="flex items-center justify-between px-3 py-2 rounded hover:bg-retro-grid/50 transition-colors group"
            >
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span
                    className={`inline-block w-2 h-2 rounded-full shrink-0 ${
                      wh.enabled ? 'led-active' : 'led-danger'
                    }`}
                    title={wh.enabled ? 'Enabled' : 'Disabled'}
                    aria-label={wh.enabled ? 'Enabled' : 'Disabled'}
                  />
                  <span className="text-sm text-zinc-200 font-mono truncate">
                    {wh.url}
                  </span>
                </div>
                <div className="flex items-center gap-2 mt-0.5 ml-4">
                  <div className="flex flex-wrap gap-1">
                    {wh.events.map((event) => (
                      <span
                        key={event}
                        className="text-[10px] px-1.5 py-0.5 rounded bg-retro-grid text-zinc-500 font-mono border border-retro-border"
                      >
                        {event}
                      </span>
                    ))}
                  </div>
                  {wh.has_secret && (
                    <span className="text-[10px] text-crt-cyan font-mono" title="Has HMAC secret configured">
                      [signed]
                    </span>
                  )}
                  {wh.project_id === null && (
                    <span className="text-[10px] text-crt-amber font-mono" title="Global webhook (not project-specific)">
                      [global]
                    </span>
                  )}
                </div>
              </div>

              <div className="flex items-center gap-1 shrink-0 sm:opacity-0 sm:group-hover:opacity-100 transition-opacity">
                <button
                  onClick={() => handleToggleEnabled(wh)}
                  className={`px-2 py-1 rounded text-[10px] font-mono border cursor-pointer transition-colors ${
                    wh.enabled
                      ? 'text-signal-yellow border-signal-yellow/30 hover:bg-signal-yellow/10 bg-transparent'
                      : 'text-crt-green border-crt-green/30 hover:bg-crt-green/10 bg-transparent'
                  }`}
                  title={wh.enabled ? 'Disable webhook' : 'Enable webhook'}
                  aria-label={wh.enabled ? `Disable ${wh.url}` : `Enable ${wh.url}`}
                >
                  {wh.enabled ? 'Disable' : 'Enable'}
                </button>
                <button
                  onClick={() => startEdit(wh)}
                  className="p-1 rounded text-zinc-500 hover:text-crt-green hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
                  title="Edit webhook"
                  aria-label={`Edit ${wh.url}`}
                >
                  <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
                    <path d="M11 2l3 3L5 14H2v-3L11 2z" />
                  </svg>
                </button>
                <button
                  onClick={() => setDeleteTarget(wh)}
                  className="p-1 rounded text-zinc-500 hover:text-signal-red hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors"
                  title="Delete webhook"
                  aria-label={`Delete ${wh.url}`}
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
      )}

      <ConfirmDialog
        open={!!deleteTarget}
        title="Delete Webhook"
        message={deleteTarget ? `Delete webhook for "${deleteTarget.url}"? This cannot be undone.` : ''}
        confirmLabel="Delete"
        danger
        onConfirm={handleDelete}
        onCancel={() => setDeleteTarget(null)}
      />
    </div>
  )
}
