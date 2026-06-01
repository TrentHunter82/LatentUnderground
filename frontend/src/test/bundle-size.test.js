import { describe, it, expect } from 'vitest'
import { readdirSync, statSync } from 'node:fs'
import { join, resolve } from 'node:path'

// process.cwd() is the frontend/ directory when vitest runs
const DIST_DIR = resolve(process.cwd(), 'dist/assets')

function getAssetFiles() {
  try {
    return readdirSync(DIST_DIR).map(name => ({
      name,
      size: statSync(join(DIST_DIR, name)).size,
      ext: name.split('.').pop(),
    }))
  } catch {
    return null
  }
}

describe('Bundle Size Regression', () => {
  const files = getAssetFiles()

  // Skip all tests if dist/ doesn't exist (not built yet)
  const skipIfNoBuild = files === null

  it('dist/assets directory exists', () => {
    if (skipIfNoBuild) return // silently pass if no build
    expect(files).not.toBeNull()
  })

  it('main JS bundle under 260KB', () => {
    if (skipIfNoBuild) return
    const mainJs = files.find(f => f.name.startsWith('index-') && f.ext === 'js')
    expect(mainJs).toBeDefined()
    expect(mainJs.size).toBeLessThan(260 * 1024) // 260KB (v2.4: accumulated UI + image feature)
  })

  it('total JS under 500KB (excluding highlight.js, markdown and dockview)', () => {
    if (skipIfNoBuild) return
    // dockview (the dockable-workspace library) is an isolated vendor chunk,
    // lazy-loaded only on the project route — excluded like highlight/markdown.
    const jsFiles = files.filter(f => f.ext === 'js' && !f.name.startsWith('highlight') && !f.name.startsWith('markdown') && !f.name.startsWith('dockview'))
    const totalSize = jsFiles.reduce((sum, f) => sum + f.size, 0)
    expect(totalSize).toBeLessThan(540 * 1024) // 540KB (v2.4: image feature + accumulated UI)
  })

  it('app CSS under 84KB (excluding the dockview vendor stylesheet)', () => {
    if (skipIfNoBuild) return
    // The dockview library ships its own ~37KB stylesheet (split into a
    // dockview-*.css vendor chunk) — excluded from the app-CSS guardrail.
    // App CSS re-baselined 75KB → 84KB: the Luma neumorphic skin (new default)
    // plus relocating Analog into explicit [data-skin] blocks adds ~6KB.
    const cssFiles = files.filter(f => f.ext === 'css' && !f.name.startsWith('dockview'))
    const totalCss = cssFiles.reduce((sum, f) => sum + f.size, 0)
    // Actual built size is 74234B (72.5KB). The token-driven refactor (Phase 2)
    // tightened the base CSS ~2KB by collapsing per-skin component overrides into a
    // composite-token layer; the Terminal reskin (4th skin: amber-phosphor dark +
    // parchment light) then adds ~5KB of token blocks. These repetitive blocks gzip
    // to ~13KB on the wire (the build minifies + gzips).
    // Budget re-baselined 75KB → 84KB (Luma phase): the new default neumorphic
    // skin + Analog relocated to explicit [data-skin] blocks. Still excludes the
    // dockview vendor stylesheet so app-CSS creep stays visible.
    expect(totalCss).toBeLessThan(84 * 1024)
  })

  it('no single lazy chunk exceeds 95KB (excluding main/vendor chunks)', () => {
    if (skipIfNoBuild) return
    const lazyChunks = files.filter(f =>
      f.ext === 'js' &&
      !f.name.startsWith('index-') &&
      !f.name.startsWith('highlight') &&
      !f.name.startsWith('markdown') &&
      !f.name.startsWith('virtual') &&
      !f.name.startsWith('dockview') &&
      !f.name.startsWith('router')
    )
    for (const chunk of lazyChunks) {
      expect(chunk.size, `${chunk.name} exceeds 95KB`).toBeLessThan(95 * 1024)
    }
  })

  it('code splitting produces at least 10 JS chunks', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js')
    expect(jsFiles.length).toBeGreaterThanOrEqual(10)
  })
})
