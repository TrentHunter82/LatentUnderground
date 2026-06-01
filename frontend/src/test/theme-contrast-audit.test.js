/**
 * WCAG AA contrast audit for every skin × mode (Claude-4 / polish gate).
 *
 * jsdom cannot resolve `var()` cascades, so this audit reads src/index.css
 * directly, resolves the token chain for each (skin × mode) context exactly as
 * the browser would, and COMPUTES the real WCAG 2.1 relative-luminance contrast
 * ratio of the two pairs that govern legibility:
 *
 *   1. body text  — --body-fg over --body-bg   → SC 1.4.3 (AA, normal text) ≥ 4.5:1
 *   2. accent     — --neon-green over --body-bg → SC 1.4.11 (non-text / UI) and
 *                   SC 1.4.3 (large text)       ≥ 3:1
 *
 * The accent (--neon-green, the skin's --color-crt-green) is the primary accent:
 * focus rings, active borders, button text, code. 3:1 is the correct floor for a
 * UI/graphical-object and large-text colour; body copy needs the stricter 4.5:1.
 *
 * Contexts are derived from SKIN_IDS, so a 5th skin is audited automatically — no
 * hardcoded skin list to drift (mirrors theme-registry-sync.test.js). The scoping
 * convention is the index.css contract: analog === base (:root / html.light), each
 * non-default skin adds html[data-skin="X"]:not(.light) (dark) and
 * html.light[data-skin="X"] (light).
 *
 * No estimation: every number below is computed from the resolved hex.
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { SKIN_IDS, DEFAULT_SKIN } from '../lib/themes'

const here = dirname(fileURLToPath(import.meta.url)) // src/test
const root = resolve(here, '../..') // frontend/
const indexCss = readFileSync(resolve(root, 'src/index.css'), 'utf-8')

// WCAG AA thresholds.
const TEXT_MIN = 4.5 // SC 1.4.3 normal text
const ACCENT_MIN = 3.0 // SC 1.4.11 non-text / SC 1.4.3 large text

// ── minimal CSS parser: selector → { prop: value } (var() chains resolved later) ──
function parseCss(src) {
  const rules = {}
  src = src.replace(/@(import|charset)[^;]*;/g, '')
  let i = 0
  const n = src.length
  const skipBalanced = () => {
    let d = 0
    for (; i < n; i++) {
      if (src[i] === '{') d++
      else if (src[i] === '}') { d--; if (!d) { i++; return } }
    }
  }
  const addDecls = (sel, body) => {
    body = body.replace(/\/\*[\s\S]*?\*\//g, '')
    if (!rules[sel]) rules[sel] = {}
    for (const d of body.split(';')) {
      const c = d.indexOf(':')
      if (c < 0) continue
      const p = d.slice(0, c).trim()
      const v = d.slice(c + 1).trim()
      if (p) rules[sel][p] = v
    }
  }
  const readBlock = () => {
    let b = ''
    let d = 1
    for (; i < n; i++) {
      if (src[i] === '{') d++
      else if (src[i] === '}') { d--; if (!d) { i++; break } }
      b += src[i]
    }
    return b
  }
  while (i < n) {
    let sel = ''
    while (i < n && src[i] !== '{' && src[i] !== '}') { sel += src[i]; i++ }
    if (i >= n) break
    if (src[i] === '}') { i++; continue }
    sel = sel.replace(/\/\*[\s\S]*?\*\//g, '').trim()
    if (sel.startsWith('@')) {
      if (sel.split(/\s+/)[0] === '@theme') { i++; addDecls(':root', readBlock()) }
      else skipBalanced()
      continue
    }
    i++
    const body = readBlock()
    for (const s of sel.split(',')) addDecls(s.trim(), body)
  }
  return rules
}

function resolveVars(value, vars, seen = 0) {
  if (seen > 50) return value
  const re = /var\(\s*(--[\w-]+)\s*(?:,\s*([^)]*))?\)/
  let v = value
  let m
  while ((m = re.exec(v))) {
    let repl = vars[m[1]]
    if (repl === undefined) repl = m[2] !== undefined ? m[2] : ''
    v = v.slice(0, m.index) + repl + v.slice(m.index + m[0].length)
    if (++seen > 50) break
  }
  if (/var\(/.test(v) && seen <= 50) return resolveVars(v, vars, seen + 1)
  return v
}

// Flatten all custom properties visible in a context (increasing specificity, last wins),
// then resolve internal var() chains so every token holds a literal value.
function buildVarMap(rules, varSel) {
  const map = {}
  for (const sel of varSel) {
    const r = rules[sel]
    if (!r) continue
    for (const [k, v] of Object.entries(r)) if (k.startsWith('--')) map[k] = v
  }
  const out = {}
  for (const k of Object.keys(map)) out[k] = resolveVars(map[k], map)
  return out
}

// ── WCAG 2.1 relative luminance + contrast ratio ──
function hexToRgb(hex) {
  const m = /^#([0-9a-f]{3}|[0-9a-f]{6})$/i.exec(hex.trim())
  if (!m) {
    throw new Error(
      `Cannot audit non-hex colour "${hex}". The contrast pairs (--body-bg/--body-fg/--neon-green) ` +
      `must resolve to an opaque hex so luminance is exact (no alpha compositing). Update this audit ` +
      `if a skin intentionally moves a contrast token to rgb()/rgba().`,
    )
  }
  let h = m[1]
  if (h.length === 3) h = h.split('').map((c) => c + c).join('')
  return [0, 2, 4].map((o) => parseInt(h.slice(o, o + 2), 16))
}
function relativeLuminance([r, g, b]) {
  const lin = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4) }
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
}
function contrastRatio(a, b) {
  const la = relativeLuminance(hexToRgb(a))
  const lb = relativeLuminance(hexToRgb(b))
  const hi = Math.max(la, lb)
  const lo = Math.min(la, lb)
  return (hi + 0.05) / (lo + 0.05)
}

// Build the (skin × mode) contexts from the registry — analog is the base skin.
function varSelFor(skin, mode) {
  if (skin === DEFAULT_SKIN) return mode === 'light' ? [':root', 'html.light'] : [':root']
  return mode === 'light'
    ? [':root', 'html.light', `html.light[data-skin="${skin}"]`]
    : [':root', `html[data-skin="${skin}"]:not(.light)`]
}

const rules = parseCss(indexCss)
const contexts = SKIN_IDS.flatMap((skin) =>
  ['dark', 'light'].map((mode) => ({ skin, mode, name: `${skin}-${mode}`, varSel: varSelFor(skin, mode) })),
)

describe('WCAG AA contrast audit — every skin × mode', () => {
  it('audits all four skins in both modes (registry-driven, no skipped contexts)', () => {
    // Guards that the registry actually expanded and parsing found the base tokens —
    // otherwise an empty/partial context set could pass vacuously.
    expect(contexts).toHaveLength(SKIN_IDS.length * 2)
    expect(SKIN_IDS.length).toBeGreaterThanOrEqual(4)
  })

  for (const ctx of contexts) {
    it(`${ctx.name}: body text ≥ ${TEXT_MIN}:1 and accent ≥ ${ACCENT_MIN}:1`, () => {
      const vars = buildVarMap(rules, ctx.varSel)
      const bg = vars['--body-bg']
      const fg = vars['--body-fg']
      const accent = vars['--neon-green']

      // Every contrast token must resolve to a concrete value in this context.
      expect(bg, `${ctx.name}: --body-bg unresolved`).toBeTruthy()
      expect(fg, `${ctx.name}: --body-fg unresolved`).toBeTruthy()
      expect(accent, `${ctx.name}: --neon-green unresolved`).toBeTruthy()
      expect(bg, `${ctx.name}: --body-bg still contains var()`).not.toMatch(/var\(/)
      expect(fg, `${ctx.name}: --body-fg still contains var()`).not.toMatch(/var\(/)
      expect(accent, `${ctx.name}: --neon-green still contains var()`).not.toMatch(/var\(/)

      const textRatio = contrastRatio(fg, bg)
      const accentRatio = contrastRatio(accent, bg)

      expect(
        textRatio,
        `${ctx.name}: body text ${fg} on ${bg} = ${textRatio.toFixed(2)}:1 (need ≥ ${TEXT_MIN}:1, SC 1.4.3)`,
      ).toBeGreaterThanOrEqual(TEXT_MIN)
      expect(
        accentRatio,
        `${ctx.name}: accent ${accent} on ${bg} = ${accentRatio.toFixed(2)}:1 (need ≥ ${ACCENT_MIN}:1, SC 1.4.11/large-text)`,
      ).toBeGreaterThanOrEqual(ACCENT_MIN)
    })
  }
})
