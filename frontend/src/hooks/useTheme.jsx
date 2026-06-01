import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import { DEFAULT_SKIN, SKINS, isValidSkin, nextSkin } from '../lib/themes'

const ThemeContext = createContext()

const STORAGE_KEY = 'latent-theme'
const SKIN_STORAGE_KEY = 'latent-skin'

function getSystemTheme() {
  try {
    if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
      return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark'
    }
  } catch { /* ignore */ }
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

function getInitialSkin() {
  try {
    const stored = localStorage.getItem(SKIN_STORAGE_KEY)
    if (isValidSkin(stored)) return stored
    return DEFAULT_SKIN
  } catch {
    return DEFAULT_SKIN
  }
}

function resolveTheme(mode) {
  return mode === 'system' ? getSystemTheme() : mode
}

export function ThemeProvider({ children }) {
  const [mode, setMode] = useState(getInitialMode)
  // Reuse the already-resolved initial `mode` rather than reading localStorage a
  // second time — getInitialMode() is idempotent, so one read on mount suffices.
  const [resolved, setResolved] = useState(() => resolveTheme(mode))
  const [skin, setSkinState] = useState(getInitialSkin)

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
    } catch { /* ignore */ }
  }, [mode])

  // Apply skin attribute and persist (orthogonal to light/dark mode)
  useEffect(() => {
    const root = document.documentElement
    root.setAttribute('data-skin', skin)
    try {
      localStorage.setItem(SKIN_STORAGE_KEY, skin)
    } catch { /* ignore */ }
  }, [skin])

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

  const setSkin = useCallback((newSkin) => {
    if (isValidSkin(newSkin)) {
      setSkinState(newSkin)
    }
  }, [])

  const cycleSkin = useCallback(() => {
    setSkinState((s) => nextSkin(s))
  }, [])

  return (
    <ThemeContext.Provider
      value={{ theme: resolved, mode, toggleTheme, setTheme, skin, setSkin, cycleSkin, skins: SKINS }}
    >
      {children}
    </ThemeContext.Provider>
  )
}

// eslint-disable-next-line react-refresh/only-export-components
export function useTheme() {
  const ctx = useContext(ThemeContext)
  if (!ctx) throw new Error('useTheme must be used within ThemeProvider')
  return ctx
}
