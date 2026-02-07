import { createContext, useCallback, useContext, useState } from 'react'

const ToastContext = createContext(null)

let toastId = 0

export function ToastProvider({ children }) {
  const [toasts, setToasts] = useState([])

  const addToast = useCallback((message, type = 'error', duration = 4000) => {
    const id = ++toastId
    setToasts((prev) => [...prev, { id, message, type }])
    setTimeout(() => {
      setToasts((prev) => prev.filter((t) => t.id !== id))
    }, duration)
  }, [])

  const dismiss = useCallback((id) => {
    setToasts((prev) => prev.filter((t) => t.id !== id))
  }, [])

  return (
    <ToastContext.Provider value={addToast}>
      {children}
      {/* Toast container */}
      <div className="fixed bottom-4 right-4 z-50 flex flex-col gap-2 pointer-events-none">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={`pointer-events-auto px-4 py-3 rounded shadow-lg text-sm font-medium flex items-center gap-3 animate-slide-in max-w-sm font-mono ${
              t.type === 'error'
                ? 'bg-signal-red/20 text-signal-red border border-signal-red/40'
                : t.type === 'success'
                  ? 'bg-crt-green/10 text-crt-green border border-crt-green/30'
                  : 'bg-retro-grid text-zinc-200 border border-retro-border'
            }`}
          >
            <span className="flex-1">{t.message}</span>
            <button
              onClick={() => dismiss(t.id)}
              className="text-current opacity-60 hover:opacity-100 bg-transparent border-0 cursor-pointer text-lg leading-none p-0"
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
