import { createContext, useContext, useState, useEffect, useCallback } from 'react'

const ThemeContext = createContext()

const STORAGE_KEY = 'latent-theme'

function getSystemTheme() {
  try {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
    }
  } catch {}
  return 'dark'
}

function getInitialMode() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    if (stored === 'dark' || stored === 'light' || stored === 'system') return stored
    // No stored preference — default to system
    return 'system'
  } catch {
    return 'system'
  }
}

function resolveTheme(mode) {
  return mode === 'system' ? getSystemTheme() : mode
}

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(getInitialMode)
  const [resolved, setResolved] = useState(() => resolveTheme(getInitialMode()))

  // Apply theme class and persist
  useEffect(() => {
    const root = document.documentElement
    const effective = resolveTheme(mode)
    setResolved(effective)

    if (effective === 'light') {
      root.classList.add('light')
    } else {
      root.classList.remove('light')
    }
    try {
      localStorage.setItem(STORAGE_KEY, mode)
    } catch {}
  }, [mode])

  // Listen for system preference changes when mode is 'system'
  useEffect(() => {
    if (mode !== 'system') return
    if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return

    const mql = window.matchMedia('(prefers-color-scheme: light)')
    const handler = (e) => {
      const effective = e.matches ? 'light' : 'dark'
      setResolved(effective)
      const root = document.documentElement
      if (effective === 'light') {
        root.classList.add('light')
      } else {
        root.classList.remove('light')
      }
    }
    mql.addEventListener('change', handler)
    return () => mql.removeEventListener('change', handler)
  }, [mode])

  // Cycle: dark → light → system → dark
  const toggleTheme = useCallback(() => {
    setMode((m) => {
      if (m === 'dark') return 'light'
      if (m === 'light') return 'system'
      return 'dark'
    })
  }, [])

  const setTheme = useCallback((newMode) => {
    if (newMode === 'dark' || newMode === 'light' || newMode === 'system') {
      setMode(newMode)
    }
  }, [])

  return (
    <ThemeContext.Provider value={{ theme: resolved, mode, toggleTheme, setTheme }}>
      {children}
    </ThemeContext.Provider>
  )
}

export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
