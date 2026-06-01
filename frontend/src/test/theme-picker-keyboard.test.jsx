/**
 * ThemePicker keyboard navigation (Claude-4 / polish gate)
 *
 * Verifies the WAI-ARIA radiogroup pattern added to ThemePicker:
 *   - roving tabindex (single tab stop on the active radio)
 *   - Arrow/Home/End keys move selection + focus, and persist the skin
 *
 * Component/selection/axe coverage lives in phase26-theme-skins.test.jsx;
 * this file owns the keyboard-interaction contract.
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { SKINS, SKIN_IDS, DEFAULT_SKIN } from '../lib/themes'

async function renderPicker() {
  const { ThemeProvider } = await import('../hooks/useTheme')
  const { default: ThemePicker } = await import('../components/ThemePicker')
  return render(
    <ThemeProvider>
      <ThemePicker />
    </ThemeProvider>
  )
}

describe('ThemePicker — keyboard navigation', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-skin')
    document.documentElement.classList.remove('light')
  })

  it('uses a roving tabindex: only the active radio is a tab stop', async () => {
    await renderPicker()
    const radios = screen.getAllByRole('radio')
    // Default skin is analog (index 0) → it is the single tab stop.
    radios.forEach((r, i) => {
      expect(r).toHaveAttribute('tabindex', SKIN_IDS[i] === DEFAULT_SKIN ? '0' : '-1')
    })
  })

  it('ArrowDown moves selection to the next skin and updates data-skin', async () => {
    await renderPicker()
    const group = screen.getByRole('radiogroup', { name: /theme skin/i })

    await act(async () => { fireEvent.keyDown(group, { key: 'ArrowDown' }) })

    const next = SKIN_IDS[1]
    expect(document.documentElement.getAttribute('data-skin')).toBe(next)
    expect(localStorage.getItem('latent-skin')).toBe(next)
    expect(screen.getByRole('radio', { name: new RegExp(SKINS[1].label, 'i') })).toHaveAttribute('aria-checked', 'true')
    // tab stop moved with the selection
    expect(screen.getByRole('radio', { name: new RegExp(SKINS[1].label, 'i') })).toHaveAttribute('tabindex', '0')
    // focus followed the selection (roving tabindex moves focus, not just the tab stop)
    expect(screen.getByRole('radio', { name: new RegExp(SKINS[1].label, 'i') })).toHaveFocus()
  })

  it('ArrowUp from the first skin wraps to the last', async () => {
    await renderPicker()
    const group = screen.getByRole('radiogroup', { name: /theme skin/i })

    await act(async () => { fireEvent.keyDown(group, { key: 'ArrowUp' }) })

    expect(document.documentElement.getAttribute('data-skin')).toBe(SKIN_IDS[SKIN_IDS.length - 1])
  })

  // ArrowRight/ArrowLeft are aliases of ArrowDown/ArrowUp in the radiogroup
  // handler — a horizontal radiogroup must honor both axes (WAI-ARIA pattern).
  it('ArrowRight advances selection like ArrowDown', async () => {
    await renderPicker()
    const group = screen.getByRole('radiogroup', { name: /theme skin/i })

    await act(async () => { fireEvent.keyDown(group, { key: 'ArrowRight' }) })

    const next = SKIN_IDS[1]
    expect(document.documentElement.getAttribute('data-skin')).toBe(next)
    expect(localStorage.getItem('latent-skin')).toBe(next)
    expect(screen.getByRole('radio', { name: new RegExp(SKINS[1].label, 'i') })).toHaveFocus()
  })

  it('ArrowLeft from the first skin wraps to the last like ArrowUp', async () => {
    await renderPicker()
    const group = screen.getByRole('radiogroup', { name: /theme skin/i })

    await act(async () => { fireEvent.keyDown(group, { key: 'ArrowLeft' }) })

    const last = SKIN_IDS[SKIN_IDS.length - 1]
    expect(document.documentElement.getAttribute('data-skin')).toBe(last)
    expect(screen.getByRole('radio', { name: new RegExp(SKINS[SKINS.length - 1].label, 'i') })).toHaveFocus()
  })

  it('Home and End jump to the first and last skins', async () => {
    await renderPicker()
    const group = screen.getByRole('radiogroup', { name: /theme skin/i })

    await act(async () => { fireEvent.keyDown(group, { key: 'End' }) })
    expect(document.documentElement.getAttribute('data-skin')).toBe(SKIN_IDS[SKIN_IDS.length - 1])
    expect(screen.getByRole('radio', { name: new RegExp(SKINS[SKINS.length - 1].label, 'i') })).toHaveFocus()

    await act(async () => { fireEvent.keyDown(group, { key: 'Home' }) })
    expect(document.documentElement.getAttribute('data-skin')).toBe(SKIN_IDS[0])
    expect(screen.getByRole('radio', { name: new RegExp(SKINS[0].label, 'i') })).toHaveFocus()
  })
})
