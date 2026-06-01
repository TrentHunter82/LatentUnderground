/**
 * SkinToggle — the compact top-bar skin cycler (beside ThemeToggle).
 * Verifies it advances through the registry, reflects the change on <html>,
 * names the current + next skin for screen readers, and is axe-clean.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act } from '@testing-library/react'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'
import { SKIN_IDS, DEFAULT_SKIN, nextSkin, getSkin } from '../lib/themes'

expect.extend(matchers)

describe('SkinToggle', () => {
  beforeEach(() => {
    localStorage.clear()
    document.documentElement.removeAttribute('data-skin')
    document.documentElement.classList.remove('light')
    vi.resetModules()
  })

  async function renderToggle() {
    const { ThemeProvider } = await import('../hooks/useTheme')
    const { default: SkinToggle } = await import('../components/SkinToggle')
    return render(
      <ThemeProvider>
        <SkinToggle />
      </ThemeProvider>
    )
  }

  it('renders a button whose label names the current and next skin', async () => {
    await renderToggle()
    const btn = screen.getByRole('button', { name: /theme skin/i })
    expect(btn).toBeInTheDocument()
    const current = getSkin(DEFAULT_SKIN)
    const upcoming = getSkin(nextSkin(DEFAULT_SKIN))
    // Assert the exact label format, not just substrings — catches ordering or
    // wording drift (e.g. current/next swapped) a toContain pair would miss.
    expect(btn.getAttribute('aria-label')).toBe(
      `Theme skin: ${current.label}. Click to switch to ${upcoming.label}.`
    )
  })

  it('cycles through every skin and wraps, updating the data-skin attribute', async () => {
    await renderToggle()
    const btn = screen.getByRole('button', { name: /theme skin/i })
    expect(document.documentElement.getAttribute('data-skin')).toBe(DEFAULT_SKIN)
    for (let i = 1; i <= SKIN_IDS.length; i++) {
      await act(async () => { fireEvent.click(btn) })
      expect(document.documentElement.getAttribute('data-skin')).toBe(SKIN_IDS[i % SKIN_IDS.length])
    }
  })

  it('persists the cycled skin to localStorage', async () => {
    await renderToggle()
    const btn = screen.getByRole('button', { name: /theme skin/i })
    await act(async () => { fireEvent.click(btn) })
    expect(localStorage.getItem('latent-skin')).toBe(SKIN_IDS[1])
  })

  it('has no axe violations', async () => {
    const { container } = await renderToggle()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })
})
