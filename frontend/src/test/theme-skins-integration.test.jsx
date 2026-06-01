/**
 * Theme Skins â€” Integration & Registry Invariants (Claude-3 / quality gate)
 *
 * Complements Claude-2's component/picker/a11y suite (phase26-theme-skins.test.jsx)
 * and the pre-existing mode suite (phase16-theme-switching.test.jsx). This file owns
 * the integration-level guarantees that cross module boundaries:
 *   1. themes.js registry invariants (single source of truth is internally consistent)
 *   2. useTheme skin behavior against the registry (default / validate / cycle / persist)
 *   3. ORTHOGONALITY: skin axis (data-skin) and mode axis (.light class) never interfere
 *   4. Persistence survives a full remount (new ThemeProvider reads stored skin)
 *
 * Tests the REAL ThemeProvider + real registry â€” no mocks of theme internals.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, act } from '@testing-library/react'
import {
  SKINS,
  SKIN_IDS,
  DEFAULT_SKIN,
  isValidSkin,
  nextSkin,
  getSkin,
} from '../lib/themes'

const SKIN_STORAGE_KEY = 'latent-skin'
const MODE_STORAGE_KEY = 'latent-theme'

describe('Theme Skins â€” registry invariants (themes.js)', () => {
  it('exposes a non-empty registry with the expected shape', () => {
    expect(Array.isArray(SKINS)).toBe(true)
    expect(SKINS.length).toBeGreaterThanOrEqual(2)
    for (const s of SKINS) {
      expect(typeof s.id).toBe('string')
      expect(s.id).toMatch(/^[a-z][a-z0-9-]*$/) // safe as a data-skin / CSS attr value
      expect(typeof s.label).toBe('string')
      expect(s.label.length).toBeGreaterThan(0)
      expect(typeof s.tagline).toBe('string')
      expect(Array.isArray(s.swatch)).toBe(true)
      expect(s.swatch).toHaveLength(3)
      for (const c of s.swatch) expect(c).toMatch(/^#[0-9a-fA-F]{6}$/)
    }
  })

  it('SKIN_IDS mirrors SKINS and has no duplicates', () => {
    expect(SKIN_IDS).toEqual(SKINS.map((s) => s.id))
    expect(new Set(SKIN_IDS).size).toBe(SKIN_IDS.length)
  })

  it('DEFAULT_SKIN is a valid, registered skin', () => {
    expect(isValidSkin(DEFAULT_SKIN)).toBe(true)
    expect(SKIN_IDS).toContain(DEFAULT_SKIN)
  })

  it('isValidSkin accepts every registered id and rejects junk', () => {
    for (const id of SKIN_IDS) expect(isValidSkin(id)).toBe(true)
    expect(isValidSkin('nope')).toBe(false)
    expect(isValidSkin('')).toBe(false)
    expect(isValidSkin(null)).toBe(false)
    expect(isValidSkin(undefined)).toBe(false)
  })

  it('nextSkin cycles through every id exactly once before wrapping', () => {
    const seen = []
    let cur = SKIN_IDS[0]
    for (let i = 0; i < SKIN_IDS.length; i++) {
      seen.push(cur)
      cur = nextSkin(cur)
    }
    expect(new Set(seen)).toEqual(new Set(SKIN_IDS)) // visited all
    expect(cur).toBe(SKIN_IDS[0]) // wrapped back to start
  })

  it('nextSkin falls back to DEFAULT_SKIN for an unknown id', () => {
    expect(nextSkin('does-not-exist')).toBe(DEFAULT_SKIN)
  })

  it('getSkin returns the matching record, or the first skin as fallback', () => {
    expect(getSkin(DEFAULT_SKIN).id).toBe(DEFAULT_SKIN)
    expect(getSkin('bogus')).toBe(SKINS[0])
  })
})

describe('Theme Skins â€” useTheme integration & orthogonality', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.classList.remove('light')
    document.documentElement.removeAttribute('data-skin')
  })

  // Helper: render the real provider and expose live stateRef via a ref object.
  async function renderTheme() {
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const stateRef = { current: null }
    function Reader() {
      stateRef.current = useTheme()
      return null
    }
    render(
      <ThemeProvider>
        <Reader />
      </ThemeProvider>
    )
    return stateRef
  }

  it('defaults to DEFAULT_SKIN and writes data-skin on <html>', async () => {
    const stateRef = await renderTheme()
    expect(stateRef.current.skin).toBe(DEFAULT_SKIN)
    expect(document.documentElement.getAttribute('data-skin')).toBe(DEFAULT_SKIN)
    expect(localStorage.getItem(SKIN_STORAGE_KEY)).toBe(DEFAULT_SKIN)
    // exposes the full registry to consumers (for the picker)
    expect(stateRef.current.skins).toEqual(SKINS)
  })

  it('setSkin applies a valid skin to <html> and persists it', async () => {
    const stateRef = await renderTheme()
    const target = SKIN_IDS.find((id) => id !== DEFAULT_SKIN)
    await act(async () => { stateRef.current.setSkin(target) })
    expect(stateRef.current.skin).toBe(target)
    expect(document.documentElement.getAttribute('data-skin')).toBe(target)
    expect(localStorage.getItem(SKIN_STORAGE_KEY)).toBe(target)
  })

  it('setSkin ignores invalid values (no stateRef/DOM/storage change)', async () => {
    const stateRef = await renderTheme()
    const before = stateRef.current.skin
    await act(async () => { stateRef.current.setSkin('totally-invalid') })
    expect(stateRef.current.skin).toBe(before)
    expect(document.documentElement.getAttribute('data-skin')).toBe(before)
    expect(localStorage.getItem(SKIN_STORAGE_KEY)).toBe(before)
  })

  it('cycleSkin advances through the registry and wraps around', async () => {
    const stateRef = await renderTheme()
    const order = []
    order.push(stateRef.current.skin)
    for (let i = 0; i < SKIN_IDS.length; i++) {
      await act(async () => { stateRef.current.cycleSkin() })
      order.push(stateRef.current.skin)
    }
    // Started at DEFAULT_SKIN, cycled N times => back to start, all visited.
    expect(order[0]).toBe(DEFAULT_SKIN)
    expect(order[order.length - 1]).toBe(DEFAULT_SKIN)
    expect(new Set(order)).toEqual(new Set(SKIN_IDS))
  })

  it('ORTHOGONALITY: changing skin does not touch the light/dark mode', async () => {
    const stateRef = await renderTheme()
    await act(async () => { stateRef.current.setTheme('light') })
    expect(document.documentElement.classList.contains('light')).toBe(true)
    const target = SKIN_IDS.find((id) => id !== DEFAULT_SKIN)

    await act(async () => { stateRef.current.setSkin(target) })

    // Skin changed...
    expect(document.documentElement.getAttribute('data-skin')).toBe(target)
    // ...but mode is untouched.
    expect(stateRef.current.mode).toBe('light')
    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(localStorage.getItem(MODE_STORAGE_KEY)).toBe('light')
  })

  it('ORTHOGONALITY: changing skin preserves system mode (does not resolve it to light/dark)', async () => {
    const stateRef = await renderTheme()
    await act(async () => { stateRef.current.setTheme('system') })
    expect(stateRef.current.mode).toBe('system')
    const target = SKIN_IDS.find((id) => id !== DEFAULT_SKIN)

    await act(async () => { stateRef.current.setSkin(target) })

    // Skin changed...
    expect(document.documentElement.getAttribute('data-skin')).toBe(target)
    // ...but the mode stays the literal 'system' — not flipped to its resolved
    // light/dark value. The skin axis must never collapse the system preference.
    expect(stateRef.current.mode).toBe('system')
    expect(localStorage.getItem(MODE_STORAGE_KEY)).toBe('system')
  })

  it('ORTHOGONALITY: changing mode does not touch the active skin', async () => {
    const stateRef = await renderTheme()
    const target = SKIN_IDS.find((id) => id !== DEFAULT_SKIN)
    await act(async () => { stateRef.current.setSkin(target) })

    await act(async () => { stateRef.current.setTheme('light') })
    await act(async () => { stateRef.current.setTheme('dark') })

    // Mode toggled twice...
    expect(stateRef.current.mode).toBe('dark')
    expect(document.documentElement.classList.contains('light')).toBe(false)
    // ...skin survived untouched.
    expect(stateRef.current.skin).toBe(target)
    expect(document.documentElement.getAttribute('data-skin')).toBe(target)
    expect(localStorage.getItem(SKIN_STORAGE_KEY)).toBe(target)
  })

  it('persists the chosen skin across a full provider remount', async () => {
    const first = await renderTheme()
    const target = SKIN_IDS.find((id) => id !== DEFAULT_SKIN)
    await act(async () => { first.current.setSkin(target) })
    expect(localStorage.getItem(SKIN_STORAGE_KEY)).toBe(target)

    // Fresh module + fresh provider: must restore the stored skin on mount.
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const state2Ref = { current: null }
    function Reader2() {
      state2Ref.current = useTheme()
      return null
    }
    render(
      <ThemeProvider>
        <Reader2 />
      </ThemeProvider>
    )
    expect(state2Ref.current.skin).toBe(target)
    expect(document.documentElement.getAttribute('data-skin')).toBe(target)
  })

  it('falls back to DEFAULT_SKIN when localStorage holds an unknown skin', async () => {
    localStorage.setItem(SKIN_STORAGE_KEY, 'corrupted-value')
    const stateRef = await renderTheme()
    expect(stateRef.current.skin).toBe(DEFAULT_SKIN)
    expect(document.documentElement.getAttribute('data-skin')).toBe(DEFAULT_SKIN)
  })
})

