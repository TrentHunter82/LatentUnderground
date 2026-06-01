import { useRef } from 'react'
import { useTheme } from '../hooks/useTheme.jsx'
import { SKINS, SKIN_IDS } from '../lib/themes'

/**
 * Skin selector — a radiogroup of reskins, each rendered as a live swatch card.
 * Sits in the Settings "Appearance" section beside the light/dark mode toggle.
 * Skin and mode are orthogonal: this picks the palette family, the toggle picks
 * light vs dark.
 *
 * SKINS is imported directly from the registry (the single source of truth);
 * context supplies only the dynamic active skin + setter.
 *
 * Keyboard: implements the WAI-ARIA radiogroup pattern — a single tab stop
 * (roving tabindex), with Arrow/Home/End keys moving the selection and focus.
 */
export default function ThemePicker() {
  const { skin, setSkin } = useTheme()
  const btnRefs = useRef([])

  const hasSelection = SKIN_IDS.includes(skin)
  const currentIndex = hasSelection ? SKIN_IDS.indexOf(skin) : 0

  // Move selection + focus to the skin at `i` (wrapping), per the radiogroup pattern.
  const selectAt = (i) => {
    const n = SKINS.length
    const idx = ((i % n) + n) % n
    setSkin?.(SKINS[idx].id)
    btnRefs.current[idx]?.focus()
  }

  const handleKeyDown = (e) => {
    switch (e.key) {
      case 'ArrowDown':
      case 'ArrowRight':
        e.preventDefault()
        selectAt(currentIndex + 1)
        break
      case 'ArrowUp':
      case 'ArrowLeft':
        e.preventDefault()
        selectAt(currentIndex - 1)
        break
      case 'Home':
        e.preventDefault()
        selectAt(0)
        break
      case 'End':
        e.preventDefault()
        selectAt(SKINS.length - 1)
        break
      default:
        break
    }
  }

  return (
    <div
      role="radiogroup"
      aria-label="Theme skin"
      className="grid grid-cols-1 gap-2"
      onKeyDown={handleKeyDown}
    >
      {SKINS.map((s, i) => {
        const selected = s.id === skin
        const [accent, surface, secondary] = s.swatch
        return (
          <button
            key={s.id}
            ref={(el) => { btnRefs.current[i] = el }}
            type="button"
            role="radio"
            aria-checked={selected}
            // Roving tabindex: only the active radio (or the first, if none active) is a tab stop.
            tabIndex={selected || (!hasSelection && i === 0) ? 0 : -1}
            onClick={() => setSkin?.(s.id)}
            className={`flex items-center gap-3 p-2.5 rounded-md border text-left cursor-pointer transition-colors focus:outline-none focus:ring-2 focus:ring-crt-green ${
              selected
                ? 'border-crt-green bg-retro-grid'
                : 'border-retro-border bg-transparent hover:bg-retro-grid'
            }`}
          >
            {/* Live swatch — three stacked palette chips evoking a faceplate */}
            <span
              className="relative flex-shrink-0 w-10 h-10 rounded-md overflow-hidden border border-retro-border"
              style={{ backgroundColor: surface }}
              aria-hidden="true"
            >
              <span
                className="absolute left-1.5 top-1.5 w-4 h-4 rounded-full"
                style={{ backgroundColor: accent, boxShadow: `0 0 4px ${accent}80` }}
              />
              <span
                className="absolute right-1.5 bottom-1.5 w-2.5 h-2.5 rounded-full"
                style={{ backgroundColor: secondary }}
              />
            </span>

            <span className="flex-1 min-w-0">
              <span className="block text-sm font-medium text-zinc-200">{s.label}</span>
              <span className="block text-xs text-zinc-500 truncate">{s.tagline}</span>
            </span>

            {selected && (
              <svg
                width="16"
                height="16"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                className="text-crt-green flex-shrink-0"
                aria-hidden="true"
              >
                <path d="M20 6L9 17l-5-5" />
              </svg>
            )}
          </button>
        )
      })}
    </div>
  )
}
