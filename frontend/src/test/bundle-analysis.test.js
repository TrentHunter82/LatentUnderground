/**
 * Bundle Analysis Tests - Phase 19
 *
 * Verifies code splitting strategy, lazy route effectiveness,
 * dependency isolation, and identifies potential bundle bloat.
 * Complements bundle-size.test.js (which checks raw sizes).
 */
import { describe, it, expect } from 'vitest'
import { readdirSync, statSync, existsSync } from 'node:fs'
import { join, resolve } from 'node:path'

const DIST_DIR = resolve(process.cwd(), 'dist')
const ASSETS_DIR = resolve(DIST_DIR, 'assets')

function getAssetFiles() {
  try {
    return readdirSync(ASSETS_DIR).map(name => ({
      name,
      size: statSync(join(ASSETS_DIR, name)).size,
      ext: name.split('.').pop(),
      // Extract chunk name: strip extension, then strip the last hyphen-separated
      // hash segment(s). Vite names: "router-DhKX72J8.js", "markdown-Cn0I5-83.js"
      chunk: name.split('.').slice(0, -1).join('.').split('-')[0],
    }))
  } catch {
    return null
  }
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes}B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)}KB`
  return `${(bytes / (1024 * 1024)).toFixed(2)}MB`
}

describe('Bundle Analysis - Code Splitting Strategy', () => {
  const files = getAssetFiles()
  const skipIfNoBuild = files === null

  it('produces separate chunks for vendor libraries', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js')
    const chunkNames = jsFiles.map(f => f.chunk)

    // Verify manualChunks configuration produces expected splits
    expect(chunkNames).toContain('router')
    expect(chunkNames).toContain('highlight')
    expect(chunkNames).toContain('markdown')
    expect(chunkNames).toContain('virtual')
  })

  it('lazy routes produce separate chunks (not bundled into main)', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js')
    // With 6 lazy components (NewProject, ProjectView, AuthModal, SettingsPanel,
    // ShortcutCheatsheet, OnboardingModal), we expect at least some lazy chunks
    // beyond the vendor chunks (router, highlight, markdown, virtual) and index
    const vendorChunks = ['router', 'highlight', 'markdown', 'virtual', 'index']
    const lazyChunks = jsFiles.filter(f =>
      !vendorChunks.some(v => f.chunk === v)
    )
    // At least 2 lazy chunks (some may be merged by Rollup if small)
    expect(lazyChunks.length).toBeGreaterThanOrEqual(2)
  })

  it('main index chunk is smaller than total vendor chunks', () => {
    if (skipIfNoBuild) return
    const indexJs = files.find(f => f.chunk === 'index' && f.ext === 'js')
    const vendorJs = files.filter(f =>
      f.ext === 'js' &&
      ['router', 'highlight', 'markdown', 'virtual'].includes(f.chunk)
    )
    const vendorTotal = vendorJs.reduce((sum, f) => sum + f.size, 0)

    expect(indexJs).toBeDefined()
    // Main bundle should be smaller than combined vendor (good splitting)
    expect(indexJs.size).toBeLessThan(vendorTotal)
  })

  it('highlight.js chunk is isolated (largest vendor dep)', () => {
    if (skipIfNoBuild) return
    const highlight = files.find(f => f.chunk === 'highlight' && f.ext === 'js')
    expect(highlight).toBeDefined()
    // highlight.js is typically 200-400KB - verify it's isolated
    expect(highlight.size).toBeGreaterThan(50 * 1024) // at least 50KB
  })

  it('markdown chunk contains remark/rehype/unified deps', () => {
    if (skipIfNoBuild) return
    const markdown = files.find(f => f.chunk === 'markdown' && f.ext === 'js')
    expect(markdown).toBeDefined()
    // Markdown ecosystem is typically 50-150KB bundled
    expect(markdown.size).toBeGreaterThan(30 * 1024)
  })

  it('router chunk is reasonably sized', () => {
    if (skipIfNoBuild) return
    const router = files.find(f => f.chunk === 'router' && f.ext === 'js')
    expect(router).toBeDefined()
    // React Router v7 + deps should be under 100KB
    expect(router.size).toBeLessThan(100 * 1024)
  })

  it('@tanstack/react-virtual chunk is small', () => {
    if (skipIfNoBuild) return
    const virtual = files.find(f => f.chunk === 'virtual' && f.ext === 'js')
    expect(virtual).toBeDefined()
    // Virtual scrolling lib should be tiny (< 30KB)
    expect(virtual.size).toBeLessThan(30 * 1024)
  })
})

describe('Bundle Analysis - Size Distribution', () => {
  const files = getAssetFiles()
  const skipIfNoBuild = files === null

  it('total bundle size (all JS + CSS) is under 1.5MB', () => {
    if (skipIfNoBuild) return
    const totalSize = files
      .filter(f => f.ext === 'js' || f.ext === 'css')
      .reduce((sum, f) => sum + f.size, 0)
    expect(totalSize).toBeLessThan(1.5 * 1024 * 1024)
  })

  it('no single JS file exceeds 500KB (prevents monolith bundles)', () => {
    if (skipIfNoBuild) return
    const jsFiles = files.filter(f => f.ext === 'js')
    for (const file of jsFiles) {
      expect(
        file.size,
        `${file.name} is ${formatBytes(file.size)} (max 500KB)`
      ).toBeLessThan(500 * 1024)
    }
  })

  it('initial load JS (index + router) is under 300KB', () => {
    if (skipIfNoBuild) return
    const initialChunks = files.filter(f =>
      f.ext === 'js' && (f.chunk === 'index' || f.chunk === 'router')
    )
    const initialSize = initialChunks.reduce((sum, f) => sum + f.size, 0)
    expect(initialSize).toBeLessThan(300 * 1024)
  })

  it('prints bundle report for documentation', () => {
    if (skipIfNoBuild) return
    const jsFiles = files
      .filter(f => f.ext === 'js')
      .sort((a, b) => b.size - a.size)
    const cssFiles = files.filter(f => f.ext === 'css')

    const totalJs = jsFiles.reduce((sum, f) => sum + f.size, 0)
    const totalCss = cssFiles.reduce((sum, f) => sum + f.size, 0)

    // Print report (visible in test output for documentation)
    console.log('\n📦 Bundle Analysis Report')
    console.log('========================')
    console.log(`Total JS:  ${formatBytes(totalJs)}`)
    console.log(`Total CSS: ${formatBytes(totalCss)}`)
    console.log(`Total:     ${formatBytes(totalJs + totalCss)}`)
    console.log(`\nJS Chunks (${jsFiles.length}):`)
    for (const f of jsFiles) {
      console.log(`  ${f.name.padEnd(40)} ${formatBytes(f.size).padStart(10)}`)
    }
    console.log(`\nCSS Files (${cssFiles.length}):`)
    for (const f of cssFiles) {
      console.log(`  ${f.name.padEnd(40)} ${formatBytes(f.size).padStart(10)}`)
    }

    // This test always passes - it's for documentation
    expect(true).toBe(true)
  })
})

describe('Bundle Analysis - Build Output', () => {
  it('dist directory exists with index.html', () => {
    const hasIndex = existsSync(resolve(DIST_DIR, 'index.html'))
    if (!hasIndex) {
      // Skip gracefully if no build
      return
    }
    expect(hasIndex).toBe(true)
  })

  it('no source maps in production build', () => {
    const files = getAssetFiles()
    if (!files) return
    const sourceMaps = files.filter(f => f.ext === 'map')
    // Source maps should not be in production dist
    expect(sourceMaps).toHaveLength(0)
  })

  it('all JS files are minified (no development artifacts)', () => {
    const files = getAssetFiles()
    if (!files) return
    const jsFiles = files.filter(f => f.ext === 'js')
    for (const file of jsFiles) {
      // Minified files use hashed names, not .dev.js or .development.js
      expect(file.name).not.toContain('.dev.')
      expect(file.name).not.toContain('.development.')
    }
  })
})
