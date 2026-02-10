import { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react'

const ToastContext = createContext(null)

let toastId = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])
  const timeoutsRef = useRef(new Map())

  useEffect(() => {
    return () => {
      timeoutsRef.current.forEach(clearTimeout)
      timeoutsRef.current.clear()
    }
  }, [])

  const addToast = useCallback((message, type = 'error', duration = 4000, action = null) => {
    const id = ++toastId
    const effectiveDuration = action && type === 'error' ? 10000 : duration
    setToasts((prev) => [...prev, { id, message, type, action }])
    const tid = setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
      timeoutsRef.current.delete(id)
    }, effectiveDuration)
    timeoutsRef.current.set(id, tid)
  }, [])

  const dismiss = useCallback((id) => {
    clearTimeout(timeoutsRef.current.get(id))
    timeoutsRef.current.delete(id)
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  const handleAction = useCallback((id, onClick) => {
    onClick()
    dismiss(id)
  }, [dismiss])

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            role="alert"
            aria-live="polite"
            aria-atomic="true"
            className={`pointer-events-auto px-4 py-3 rounded shadow-lg text-sm font-medium flex items-center gap-3 animate-slide-in max-w-sm font-mono ${
              t.type === 'error'
                ? 'bg-signal-red/20 text-signal-red border border-signal-red/40'
                : t.type === 'success'
                  ? 'bg-crt-green/10 text-crt-green border border-crt-green/30'
                  : 'bg-retro-grid text-zinc-200 border border-retro-border'
            }`}
          >
            <span className="flex-1">{t.message}</span>
            {t.action && (
              <button
                onClick={() => handleAction(t.id, t.action.onClick)}
                className="btn-neon text-xs px-2 py-0.5"
              >
                {t.action.label}
              </button>
            )}
            <button
              onClick={() => dismiss(t.id)}
              className="text-current opacity-60 hover:opacity-100 bg-transparent border-0 cursor-pointer text-lg leading-none p-0"
              aria-label="Dismiss notification"
            >
              &times;
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}

export function useToast() {
  const addToast = useContext(ToastContext)
  if (!addToast) throw new Error('useToast must be used within ToastProvider')
  return addToast
}

const noop = () => {}

/** Like useToast but returns a no-op if outside ToastProvider (safe for tests) */
export function useSafeToast() {
  return useContext(ToastContext) || noop
}
