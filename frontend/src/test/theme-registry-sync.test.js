/**
 * Theme registry single-source-of-truth guard (Claude-4 / polish gate).
 *
 * The skin registry in src/lib/themes.js (SKIN_IDS) is duplicated, by necessity,
 * in two places that cannot import it:
 *   1. index.html — the no-flash bootstrap script validates the persisted skin
 *      against a hardcoded id list before React hydrates.
 *   2. src/index.css — each non-default skin needs a dark and a light CSS block.
 *
 * Those copies must not drift from SKIN_IDS. There is no build step wiring them
 * together, so this test is the mechanical enforcement: adding/removing a skin in
 * themes.js fails here until index.html and index.css are updated to match.
 *
 * (Addresses the drift hazards surfaced in the theme-system review: a new skin
 * would otherwise be silently rejected by the bootstrap and render with the base
 * "analog" palette, with no error — only a flash on hydration.)
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, resolve } from 'node:path'
import { SKIN_IDS, DEFAULT_SKIN } from '../lib/themes'

const here = dirname(fileURLToPath(import.meta.url)) // src/test
const root = resolve(here, '../..') // frontend/
const indexHtml = readFileSync(resolve(root, 'index.html'), 'utf-8')
const indexCss = readFileSync(resolve(root, 'src/index.css'), 'utf-8')

describe('theme registry single source of truth', () => {
  it('index.html bootstrap validates exactly the registry skin ids', () => {
    // Bootstrap form: skin !== 'analog' && skin !== 'obsidian' && ...
    const bootstrapIds = [...indexHtml.matchAll(/skin !== '([a-z0-9-]+)'/g)].map((m) => m[1])
    expect(bootstrapIds.length).toBeGreaterThan(0)
    expect(new Set(bootstrapIds)).toEqual(new Set(SKIN_IDS))
  })

  it('index.html bootstrap falls back to the default skin', () => {
    expect(indexHtml).toContain(`skin = '${DEFAULT_SKIN}'`)
  })

  it('every non-default skin has a dark and a light CSS block in index.css', () => {
    for (const id of SKIN_IDS) {
      if (id === DEFAULT_SKIN) continue
      expect(indexCss, `missing dark block for skin "${id}"`).toContain(`html[data-skin="${id}"]:not(.light)`)
      expect(indexCss, `missing light block for skin "${id}"`).toContain(`html.light[data-skin="${id}"]`)
    }
  })

  it('the default skin intentionally has no override block (falls through to base styles)', () => {
    // Documents the zero-regression design: analog === base, so it must NOT be
    // re-declared. If this ever fails, the default-skin contract changed.
    expect(indexCss).not.toContain(`html[data-skin="${DEFAULT_SKIN}"]`)
  })
})
