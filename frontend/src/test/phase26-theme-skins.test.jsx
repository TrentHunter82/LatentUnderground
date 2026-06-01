/**
 * Phase 26 - Theme Skins (reskins) Tests
 *
 * Covers the multi-skin layer added on top of the existing light/dark mode:
 * - themes.js registry integrity
 * - ThemeProvider skin state: default, persistence, data-skin attribute,
 *   validation, cycling, and restore-on-mount
 * - ThemePicker component: radiogroup semantics, selection, axe audit
 *
 * The orthogonal light/dark mode behaviour is covered by phase16-theme-switching.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'
import { SKINS, SKIN_IDS, DEFAULT_SKIN, isValidSkin, nextSkin, getSkin } from '../lib/themes'

expect.extend(matchers)

describe('Phase 26 - themes.js registry', () => {
  it('exposes a non-empty list of skins with required fields', () => {
    expect(SKINS.length).toBeGreaterThanOrEqual(3)
    for (const s of SKINS) {
      expect(typeof s.id).toBe('string')
      expect(typeof s.label).toBe('string')
      expect(typeof s.tagline).toBe('string')
      expect(Array.isArray(s.swatch)).toBe(true)
      expect(s.swatch).toHaveLength(3)
      // swatch entries are hex colors
      for (const hex of s.swatch) {
        expect(hex).toMatch(/^#[0-9A-Fa-f]{6}$/)
      }
    }
  })

  it('has unique skin ids and a valid default', () => {
    expect(new Set(SKIN_IDS).size).toBe(SKIN_IDS.length)
    expect(SKIN_IDS).toContain(DEFAULT_SKIN)
    expect(DEFAULT_SKIN).toBe('luma')
  })

  it('includes the analog, obsidian, blueprint and terminal reskins', () => {
    expect(SKIN_IDS).toContain('analog')
    expect(SKIN_IDS).toContain('obsidian')
    expect(SKIN_IDS).toContain('blueprint')
    expect(SKIN_IDS).toContain('terminal')
  })

  it('isValidSkin accepts known ids and rejects others', () => {
    expect(isValidSkin('analog')).toBe(true)
    expect(isValidSkin('obsidian')).toBe(true)
    expect(isValidSkin('nope')).toBe(false)
    expect(isValidSkin(undefined)).toBe(false)
    expect(isValidSkin(null)).toBe(false)
  })

  it('nextSkin cycles through all ids and wraps around', () => {
    const seen = []
    let cur = SKIN_IDS[0]
    for (let i = 0; i < SKIN_IDS.length; i++) {
      seen.push(cur)
      cur = nextSkin(cur)
    }
    expect(seen).toEqual(SKIN_IDS)
    // wrapped back to the start
    expect(cur).toBe(SKIN_IDS[0])
  })

  it('nextSkin falls back to default for unknown id', () => {
    expect(nextSkin('garbage')).toBe(DEFAULT_SKIN)
  })

  it('getSkin returns the matching entry or the first as fallback', () => {
    expect(getSkin('obsidian').id).toBe('obsidian')
    expect(getSkin('garbage')).toBe(SKINS[0])
  })
})

describe('Phase 26 - ThemeProvider skin dimension', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-skin')
    document.documentElement.classList.remove('light')
    vi.resetModules()
  })

  function renderWithReader(ThemeProvider, useTheme) {
    let state = null
    function Reader() {
      state = useTheme()
      return null
    }
    render(
      <ThemeProvider>
        <Reader />
      </ThemeProvider>
    )
    return () => state
  }

  it('defaults to the luma skin and sets the data-skin attribute', async () => {
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const get = renderWithReader(ThemeProvider, useTheme)

    expect(get().skin).toBe('luma')
    expect(document.documentElement.getAttribute('data-skin')).toBe('luma')
  })

  it('setSkin updates state, attribute, and localStorage', async () => {
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const get = renderWithReader(ThemeProvider, useTheme)

    await act(async () => { get().setSkin('obsidian') })

    expect(get().skin).toBe('obsidian')
    expect(document.documentElement.getAttribute('data-skin')).toBe('obsidian')
    expect(localStorage.getItem('latent-skin')).toBe('obsidian')
  })

  it('setSkin rejects invalid skin ids', async () => {
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const get = renderWithReader(ThemeProvider, useTheme)

    await act(async () => { get().setSkin('blueprint') })
    expect(get().skin).toBe('blueprint')

    await act(async () => { get().setSkin('not-a-skin') })
    // unchanged
    expect(get().skin).toBe('blueprint')
  })

  it('cycleSkin advances through the registry and wraps', async () => {
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const get = renderWithReader(ThemeProvider, useTheme)

    const order = [get().skin]
    for (let i = 0; i < SKIN_IDS.length; i++) {
      await act(async () => { get().cycleSkin() })
      order.push(get().skin)
    }
    // after N cycles we are back to the starting skin
    expect(order[0]).toBe('luma')
    expect(order[order.length - 1]).toBe('luma')
    // every skin was visited
    expect(new Set(order)).toEqual(new Set(SKIN_IDS))
  })

  it('restores a stored skin preference on mount', async () => {
    localStorage.setItem('latent-skin', 'blueprint')
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const get = renderWithReader(ThemeProvider, useTheme)

    expect(get().skin).toBe('blueprint')
    expect(document.documentElement.getAttribute('data-skin')).toBe('blueprint')
  })

  it('ignores a corrupt stored skin preference', async () => {
    localStorage.setItem('latent-skin', 'corrupt-value')
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const get = renderWithReader(ThemeProvider, useTheme)

    expect(get().skin).toBe('luma')
  })

  it('skin is orthogonal to mode — changing skin keeps the light class', async () => {
    const { ThemeProvider, useTheme } = await import('../hooks/useTheme')
    const get = renderWithReader(ThemeProvider, useTheme)

    await act(async () => { get().setTheme('light') })
    await act(async () => { get().setSkin('obsidian') })

    expect(document.documentElement.classList.contains('light')).toBe(true)
    expect(document.documentElement.getAttribute('data-skin')).toBe('obsidian')
    expect(get().mode).toBe('light')
  })
})

describe('Phase 26 - ThemePicker', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-skin')
    vi.resetModules()
  })

  async function renderPicker() {
    const { ThemeProvider } = await import('../hooks/useTheme')
    const { default: ThemePicker } = await import('../components/ThemePicker')
    return render(
      <ThemeProvider>
        <ThemePicker />
      </ThemeProvider>
    )
  }

  it('renders a radiogroup with one radio per skin', async () => {
    await renderPicker()
    expect(screen.getByRole('radiogroup', { name: /theme skin/i })).toBeInTheDocument()
    const radios = screen.getAllByRole('radio')
    expect(radios).toHaveLength(SKINS.length)
  })

  it('marks the active skin as checked', async () => {
    await renderPicker()
    const luma = screen.getByRole('radio', { name: /luma/i })
    expect(luma).toHaveAttribute('aria-checked', 'true')
    const obsidian = screen.getByRole('radio', { name: /obsidian/i })
    expect(obsidian).toHaveAttribute('aria-checked', 'false')
  })

  it('selecting a skin updates checked state and the document attribute', async () => {
    await renderPicker()
    const blueprint = screen.getByRole('radio', { name: /blueprint/i })

    await act(async () => { fireEvent.click(blueprint) })

    expect(blueprint).toHaveAttribute('aria-checked', 'true')
    expect(document.documentElement.getAttribute('data-skin')).toBe('blueprint')
    expect(localStorage.getItem('latent-skin')).toBe('blueprint')
  })

  it('shows each skin label and tagline', async () => {
    await renderPicker()
    for (const s of SKINS) {
      expect(screen.getByText(s.label)).toBeInTheDocument()
      expect(screen.getByText(s.tagline)).toBeInTheDocument()
    }
  })

  it('has no axe violations', async () => {
    const { container } = await renderPicker()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
