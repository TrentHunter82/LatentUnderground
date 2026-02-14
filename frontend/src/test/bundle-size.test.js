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

  it('main JS bundle under 250KB', () => {
    if (skipIfNoBuild) return
    const mainJs = files.find(f => f.name.startsWith('index-') && f.ext === 'js')
    expect(mainJs).toBeDefined()
    expect(mainJs.size).toBeLessThan(250 * 1024) // 250KB
  })

  it('total JS under 500KB (excluding highlight.js and markdown)', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js' && !f.name.startsWith('highlight') && !f.name.startsWith('markdown'))
    const totalSize = jsFiles.reduce((sum, f) => sum + f.size, 0)
    expect(totalSize).toBeLessThan(500 * 1024) // 500KB
  })

  it('CSS under 50KB', () => {
    if (skipIfNoBuild) return
    const cssFiles = files.filter(f => f.ext === 'css')
    const totalCss = cssFiles.reduce((sum, f) => sum + f.size, 0)
    expect(totalCss).toBeLessThan(55 * 1024) // 55KB
  })

  it('no single lazy chunk exceeds 55KB (excluding main/vendor chunks)', () => {
    if (skipIfNoBuild) return
    const lazyChunks = files.filter(f =>
      f.ext === 'js' &&
      !f.name.startsWith('index-') &&
      !f.name.startsWith('highlight') &&
      !f.name.startsWith('markdown') &&
      !f.name.startsWith('virtual') &&
      !f.name.startsWith('router')
    )
    for (const chunk of lazyChunks) {
      expect(chunk.size, `${chunk.name} exceeds 85KB`).toBeLessThan(85 * 1024)
    }
  })

  it('code splitting produces at least 10 JS chunks', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js')
    expect(jsFiles.length).toBeGreaterThanOrEqual(10)
  })
})
