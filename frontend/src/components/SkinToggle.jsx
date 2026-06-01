import { useTheme } from '../hooks/useTheme.jsx'
import { getSkin, nextSkin } from '../lib/themes'

/**
 * Compact top-bar skin cycler — sits beside ThemeToggle. One click advances to
 * the next reskin (analog → obsidian → blueprint → terminal → …), orthogonal to
 * the light/dark toggle. The full radiogroup picker lives in Settings; this is
 * the quick "try the next look" affordance.
 *
 * A live accent swatch (the current skin's primary color) doubles as the icon so
 * the control previews what's active. Accessible: the label names the current
 * skin and the one a click will switch to.
 */
export default function SkinToggle() {
  const { skin, cycleSkin } = useTheme()
  const current = getSkin(skin)
  const upcoming = getSkin(nextSkin(skin))
  const [accent, surface, secondary] = current.swatch

  return (
    <button
      onClick={cycleSkin}
      className="p-1.5 rounded-md text-zinc-400 hover:bg-retro-grid bg-transparent border-0 cursor-pointer transition-colors flex items-center"
      title={`Skin: ${current.label} (click for ${upcoming.label})`}
      aria-label={`Theme skin: ${current.label}. Click to switch to ${upcoming.label}.`}
    >
      {/* Live palette chip — a tiny faceplate previewing the active skin */}
      <span
        className="relative w-4 h-4 rounded-full overflow-hidden border border-retro-border block"
        style={{ backgroundColor: surface }}
        aria-hidden="true"
      >
        <span
          className="absolute inset-y-0 left-0 w-1/2"
          style={{ backgroundColor: accent }}
        />
        <span
          className="absolute right-0 bottom-0 w-1.5 h-1.5 rounded-full"
          style={{ backgroundColor: secondary }}
        />
      </span>
    </button>
  )
}
