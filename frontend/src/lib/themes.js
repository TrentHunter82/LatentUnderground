/**
 * Theme skin registry — single source of truth for the visual reskins.
 *
 * A "skin" is a palette family (Analog / Obsidian / Blueprint). It is orthogonal
 * to the light/dark "mode" handled by useTheme: every skin has both a dark and a
 * light variant defined in index.css. The skin is applied to <html> via the
 * `data-skin` attribute; the default skin ("analog") intentionally has no CSS
 * override block so it falls through to the base styles (zero-regression).
 *
 * `swatch` is [accent, surface, secondary] — used to render live preview chips
 * in the ThemePicker. Keep these in sync with the corresponding CSS blocks.
 */

export const DEFAULT_SKIN = 'luma'

export const SKINS = [
  {
    id: 'luma',
    label: 'Luma',
    tagline: 'Soft-UI neumorphic graphite',
    // amber accent · graphite body · steel-blue secondary
    swatch: ['#E8923C', '#26282C', '#6FB0C9'],
  },
  {
    id: 'analog',
    label: 'Analog',
    tagline: 'Vintage mint control panel',
    // mint accent · warm charcoal body · orange toggle
    swatch: ['#80C8B0', '#12120E', '#E87838'],
  },
  {
    id: 'obsidian',
    label: 'Obsidian',
    tagline: 'Blacked-out industrial',
    // chrome accent · near-black body · steel secondary
    swatch: ['#E8E8E8', '#060606', '#92A6AE'],
  },
  {
    id: 'blueprint',
    label: 'Blueprint',
    tagline: 'Technical drafting lab',
    // blueprint blue accent · cool paper body · annotation red
    swatch: ['#2E6E8E', '#E7EAEC', '#B0413E'],
  },
  {
    id: 'terminal',
    label: 'Terminal',
    tagline: 'Amber phosphor CRT',
    // amber phosphor accent · warm-black glass body · red-orange secondary
    swatch: ['#FFB000', '#0B0800', '#FF7043'],
  },
]

export const SKIN_IDS = SKINS.map((s) => s.id)

export function isValidSkin(id) {
  return SKIN_IDS.includes(id)
}

/** Next skin in the registry, wrapping around. Used by cycleSkin(). */
export function nextSkin(id) {
  const i = SKIN_IDS.indexOf(id)
  if (i === -1) return DEFAULT_SKIN
  return SKIN_IDS[(i + 1) % SKIN_IDS.length]
}

export function getSkin(id) {
  return SKINS.find((s) => s.id === id) || SKINS[0]
}
