import { useState, useEffect, useRef, useCallback } from 'react'
import { useTheme } from '../hooks/useTheme.jsx'
import { useHealthCheck } from '../hooks/useHealthCheck'
import { useNotifications } from '../hooks/useNotifications'
import { getStoredApiKey, clearApiKey } from '../lib/api'
import ConfirmDialog from './ConfirmDialog'

export default function SettingsPanel({ open, onClose, onOpenAuth }) {
  const { theme, toggleTheme } = useTheme()
  const { status, latency } = useHealthCheck()
  const { permission, enabled, setEnabled, requestPermission } = useNotifications()
  const [hasApiKey, setHasApiKey] = useState(false)
  const [showClearConfirm, setShowClearConfirm] = useState(false)
  const panelRef = useRef(null)

  useEffect(() => {
    setHasApiKey(!!getStoredApiKey())
  }, [open])

  useEffect(() => {
    if (!open || !panelRef.current) return
    const focusable = panelRef.current.querySelectorAll('button')
    focusable[0]?.focus()
  }, [open])

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Escape') {
      onClose()
      return
    }
    if (e.key === 'Tab') {
      const panel = panelRef.current
      if (!panel) return
      const focusable = panel.querySelectorAll(
        'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
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

  const handleClearKey = () => {
    clearApiKey()
    setHasApiKey(false)
    setShowClearConfirm(false)
  }

  const handleNotificationToggle = async () => {
    if (!enabled && permission !== 'granted') {
      const result = await requestPermission()
      if (result !== 'granted') return
    }
    setEnabled(!enabled)
  }

  const statusColor = {
    healthy: 'led-active',
    slow: 'led-warning',
    degraded: 'led-warning',
    disconnected: 'led-danger',
  }[status] || 'led-inactive'

  const statusLabel = {
    healthy: 'Healthy',
    slow: 'Slow',
    degraded: 'Degraded',
    disconnected: 'Disconnected',
  }[status] || 'Unknown'

  if (!open) return null

  return (
    <>
      <div
        className="fixed inset-0 bg-black/60 z-50"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        className="fixed right-0 top-0 h-full w-80 max-w-full z-50 bg-retro-dark border-l border-retro-border shadow-2xl flex flex-col animate-slide-in"
        onKeyDown={handleKeyDown}
      >
        <div className="flex items-center justify-between p-4 border-b border-retro-border">
          <h2 id="settings-title" className="text-lg font-semibold neon-green m-0">Settings</h2>
          <button
            onClick={onClose}
            className="text-zinc-400 hover:text-zinc-200 transition-colors p-1 bg-transparent border-0 cursor-pointer"
            aria-label="Close settings"
          >
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
              <path d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-4 space-y-6">
          <section>
            <h3 className="text-xs uppercase tracking-widest text-zinc-500 font-mono mb-3">Appearance</h3>
            <div className="retro-panel p-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-zinc-200">Theme</div>
                  <div className="text-xs text-zinc-500 mt-0.5 capitalize">{theme}</div>
                </div>
                <button
                  onClick={toggleTheme}
                  className="relative w-10 h-5 rounded-full transition-colors duration-200 border-0 cursor-pointer focus:outline-none focus:ring-2 focus:ring-crt-green"
                  style={{ backgroundColor: theme === 'dark' ? '#3C3C30' : '#80C8B0' }}
                  aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
                  aria-pressed={theme === 'light'}
                >
                  <span
                    className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full transition-transform duration-200 shadow-sm"
                    style={{
                      backgroundColor: theme === 'dark' ? '#80C8B0' : '#12120e',
                      transform: theme === 'light' ? 'translateX(20px)' : 'translateX(0)',
                    }}
                  />
                </button>
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-xs uppercase tracking-widest text-zinc-500 font-mono mb-3">Authentication</h3>
            <div className="retro-panel p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm text-zinc-200">API Key</div>
                <div className={`text-xs font-mono ${hasApiKey ? 'neon-green' : 'text-zinc-500'}`}>
                  {hasApiKey ? 'Configured' : 'Not set'}
                </div>
              </div>
              <div className="flex gap-2">
                <button onClick={onOpenAuth} className="btn-neon flex-1 text-xs py-1.5">
                  Change Key
                </button>
                {hasApiKey && (
                  <button
                    onClick={() => setShowClearConfirm(true)}
                    className="btn-neon-danger text-xs py-1.5 px-3"
                    aria-label="Clear API key"
                  >
                    Clear
                  </button>
                )}
              </div>
            </div>
          </section>

          <section>
            <h3 className="text-xs uppercase tracking-widest text-zinc-500 font-mono mb-3">Notifications</h3>
            <div className="retro-panel p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-sm font-medium text-zinc-200">Browser Notifications</div>
                  <div className="text-xs text-zinc-500 mt-0.5">
                    {permission === 'granted' ? 'Allowed' : permission === 'denied' ? 'Blocked' : 'Not requested'}
                  </div>
                </div>
                <button
                  onClick={handleNotificationToggle}
                  disabled={permission === 'denied'}
                  className="relative w-10 h-5 rounded-full transition-colors duration-200 border-0 cursor-pointer focus:outline-none focus:ring-2 focus:ring-crt-green disabled:opacity-50 disabled:cursor-not-allowed"
                  style={{ backgroundColor: enabled ? '#80C8B0' : '#3C3C30' }}
                  aria-label={`${enabled ? 'Disable' : 'Enable'} notifications`}
                  aria-pressed={enabled}
                >
                  <span
                    className="absolute top-0.5 left-0.5 w-4 h-4 rounded-full transition-transform duration-200 shadow-sm"
                    style={{
                      backgroundColor: enabled ? '#12120e' : '#80C8B0',
                      transform: enabled ? 'translateX(20px)' : 'translateX(0)',
                    }}
                  />
                </button>
              </div>
              {permission === 'denied' && (
                <div className="text-xs text-zinc-500">
                  Notifications blocked by browser. Enable in browser settings.
                </div>
              )}
            </div>
          </section>

          <section>
            <h3 className="text-xs uppercase tracking-widest text-zinc-500 font-mono mb-3">System Info</h3>
            <div className="retro-panel p-3 space-y-3">
              <div className="flex items-center justify-between">
                <div className="text-sm text-zinc-200">Server Status</div>
                <div className="flex items-center gap-2">
                  <span className={`w-2 h-2 rounded-full ${statusColor}`} aria-hidden="true" />
                  <span className="text-xs text-zinc-400">{statusLabel}</span>
                  {latency !== null && (
                    <span className="text-xs text-zinc-500 font-mono">({latency}ms)</span>
                  )}
                </div>
              </div>
              <div className="flex items-center justify-between">
                <div className="text-sm text-zinc-200">Rate Limit</div>
                <div className="text-xs text-zinc-400 font-mono">30 req/min</div>
              </div>
              <div className="pt-2 border-t border-retro-border">
                <div className="text-xs text-zinc-500 font-mono">Latent Underground v{typeof __APP_VERSION__ !== 'undefined' ? __APP_VERSION__ : '0.1'}</div>
              </div>
            </div>
          </section>
        </div>
      </div>

      <ConfirmDialog
        open={showClearConfirm}
        title="Clear API Key?"
        message="This will remove your stored API key. Re-enter it to access protected endpoints."
        confirmLabel="Clear Key"
        danger={true}
        onConfirm={handleClearKey}
        onCancel={() => setShowClearConfirm(false)}
      />
    </>
  )
}
