/**
 * Phase 10 Accessibility Tests
 *
 * Tests accessibility for the 3 new Phase 10 modal components:
 * SettingsPanel, ShortcutCheatsheet, OnboardingModal.
 *
 * Covers axe-core automated audits, ARIA attributes, focus traps,
 * keyboard navigation, and semantic HTML.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { axe } from 'vitest-axe'
import * as matchers from 'vitest-axe/matchers'
import { createApiMock } from './test-utils'

expect.extend(matchers)

// Mock api (SettingsPanel uses getStoredApiKey, clearApiKey)
vi.mock('../lib/api', () => createApiMock({
  createAbortable: vi.fn(() => ({ signal: undefined, abort: vi.fn() })),
  getProjects: vi.fn(() => Promise.resolve([])),
  getStoredApiKey: vi.fn(() => null),
  clearApiKey: vi.fn(),
  getProjectQuota: vi.fn(() => Promise.resolve({ project_id: 1, quota: {}, usage: {} })),
  getProjectHealth: vi.fn(() => Promise.resolve({ project_id: 1, crash_rate: 0, status: 'healthy', trend: 'stable', run_count: 0 })),
  getHealthTrends: vi.fn(() => Promise.resolve({ projects: [], computed_at: new Date().toISOString() })),
  getRunCheckpoints: vi.fn(() => Promise.resolve({ run_id: 1, checkpoints: [], total: 0 })),
}))

// Mock useHealthCheck (SettingsPanel uses status/latency)
vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 42, data: { status: 'ok', app: { active_processes: 0 } } }),
}))

// Mock useTheme (SettingsPanel uses theme/toggleTheme)
vi.mock('../hooks/useTheme.jsx', () => ({
  useTheme: () => ({ theme: 'dark', toggleTheme: vi.fn() }),
  ThemeProvider: ({ children }) => children,
}))

// Mock useNotifications (SettingsPanel uses permission/enabled/setEnabled)
vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({
    notify: vi.fn(),
    permission: 'granted',
    enabled: false,
    setEnabled: vi.fn(),
    requestPermission: vi.fn(() => Promise.resolve('granted')),
  }),
}))

import SettingsPanel from '../components/SettingsPanel'
import ShortcutCheatsheet from '../components/ShortcutCheatsheet'
import OnboardingModal from '../components/OnboardingModal'
import { KEYBOARD_SHORTCUTS } from '../lib/constants'


// =============================================================================
// SettingsPanel Accessibility (5 tests)
// =============================================================================
describe('SettingsPanel Accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('has no axe violations', async () => {
    const { container } = render(
      <SettingsPanel open={true} onClose={vi.fn()} onOpenAuth={vi.fn()} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('dialog has correct ARIA attributes (role, aria-modal, aria-labelledby)', () => {
    render(
      <SettingsPanel open={true} onClose={vi.fn()} onOpenAuth={vi.fn()} />
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'settings-title')

    // Verify the title element exists and matches the labelledby reference
    const titleEl = document.getElementById('settings-title')
    expect(titleEl).toBeInTheDocument()
    expect(titleEl).toHaveTextContent('Settings')
  })

  it('focus moves to first interactive element when opened', async () => {
    render(
      <SettingsPanel open={true} onClose={vi.fn()} onOpenAuth={vi.fn()} />
    )
    // The component focuses the first button inside panelRef on open (with a microtask delay).
    const closeBtn = screen.getByLabelText('Close settings')
    await waitFor(() => {
      expect(document.activeElement).toBe(closeBtn)
    })
  })

  it('Escape key closes the panel', () => {
    const onClose = vi.fn()
    render(
      <SettingsPanel open={true} onClose={onClose} onOpenAuth={vi.fn()} />
    )
    const dialog = screen.getByRole('dialog')
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('Tab key cycles through focusable elements without escaping dialog', () => {
    render(
      <SettingsPanel open={true} onClose={vi.fn()} onOpenAuth={vi.fn()} />
    )
    const dialog = screen.getByRole('dialog')

    // Gather all focusable elements inside the dialog
    const focusable = dialog.querySelectorAll(
      'button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])'
    )
    expect(focusable.length).toBeGreaterThan(1)

    const first = focusable[0]
    const last = focusable[focusable.length - 1]

    // Focus the last element, then Tab forward - should wrap to first
    last.focus()
    expect(document.activeElement).toBe(last)
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: false })
    expect(document.activeElement).toBe(first)

    // Focus first element, then Shift+Tab backward - should wrap to last
    first.focus()
    expect(document.activeElement).toBe(first)
    fireEvent.keyDown(dialog, { key: 'Tab', shiftKey: true })
    expect(document.activeElement).toBe(last)
  })
})


// =============================================================================
// ShortcutCheatsheet Accessibility (4 tests)
// =============================================================================
describe('ShortcutCheatsheet Accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('has no axe violations', async () => {
    const { container } = render(
      <ShortcutCheatsheet open={true} onClose={vi.fn()} />
    )
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('dialog has correct ARIA attributes (role, aria-modal, aria-labelledby)', () => {
    render(
      <ShortcutCheatsheet open={true} onClose={vi.fn()} />
    )
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'shortcuts-dialog-title')

    // Verify the title element exists and matches the labelledby reference
    const titleEl = document.getElementById('shortcuts-dialog-title')
    expect(titleEl).toBeInTheDocument()
    expect(titleEl).toHaveTextContent('Keyboard Shortcuts')
  })

  it('keyboard shortcuts are rendered with kbd elements', () => {
    const { container } = render(
      <ShortcutCheatsheet open={true} onClose={vi.fn()} />
    )
    const kbdElements = container.querySelectorAll('kbd')
    // Each shortcut entry has at least one kbd element; compound shortcuts (e.g. Ctrl+K) have two.
    // Count total keys across all KEYBOARD_SHORTCUTS
    const expectedMinKbds = KEYBOARD_SHORTCUTS.length
    expect(kbdElements.length).toBeGreaterThanOrEqual(expectedMinKbds)

    // Verify some specific key labels exist inside kbd elements
    const kbdTexts = Array.from(kbdElements).map((el) => el.textContent)
    expect(kbdTexts).toContain('Ctrl')
    expect(kbdTexts).toContain('Escape')
  })

  it('Escape key closes the cheatsheet', () => {
    const onClose = vi.fn()
    render(
      <ShortcutCheatsheet open={true} onClose={onClose} />
    )
    const dialog = screen.getByRole('dialog')
    fireEvent.keyDown(dialog, { key: 'Escape' })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})


// =============================================================================
// OnboardingModal Accessibility (6 tests)
// =============================================================================
describe('OnboardingModal Accessibility', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    localStorage.removeItem('lu_onboarding_complete')
  })

  const renderOnboarding = (props = {}) =>
    render(
      <MemoryRouter>
        <OnboardingModal open={true} onClose={vi.fn()} {...props} />
      </MemoryRouter>
    )

  it('has no axe violations on step 0 (Welcome)', async () => {
    const { container } = renderOnboarding()
    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('has no axe violations on step 3 (final step)', async () => {
    const { container } = renderOnboarding()

    // Navigate to step 3 (final) by clicking NEXT three times
    await act(async () => { fireEvent.click(screen.getByText('NEXT')) })
    await act(async () => { fireEvent.click(screen.getByText('NEXT')) })
    await act(async () => { fireEvent.click(screen.getByText('NEXT')) })

    expect(screen.getByText('CREATE FIRST PROJECT')).toBeInTheDocument()

    const results = await axe(container)
    expect(results).toHaveNoViolations()
  })

  it('dialog has correct ARIA attributes (role, aria-modal, aria-labelledby)', () => {
    renderOnboarding()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toBeInTheDocument()
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'onboarding-title')

    const titleEl = document.getElementById('onboarding-title')
    expect(titleEl).toBeInTheDocument()
    expect(titleEl).toHaveTextContent('Welcome to Latent Underground')
  })

  it('step navigation with Next button advances through all steps', async () => {
    renderOnboarding()

    // Step 0: Welcome
    expect(screen.getByText('Welcome to Latent Underground')).toBeInTheDocument()

    // Step 1: Configure
    await act(async () => { fireEvent.click(screen.getByText('NEXT')) })
    expect(screen.getByText('Create & Configure')).toBeInTheDocument()

    // Step 2: Monitor
    await act(async () => { fireEvent.click(screen.getByText('NEXT')) })
    expect(screen.getByText('Launch & Monitor')).toBeInTheDocument()

    // Step 3: Notifications (final)
    await act(async () => { fireEvent.click(screen.getByText('NEXT')) })
    expect(screen.getByText('Stay Informed')).toBeInTheDocument()
    expect(screen.getByText('CREATE FIRST PROJECT')).toBeInTheDocument()
  })

  it('Back button is disabled on first step', () => {
    renderOnboarding()
    const backButton = screen.getByText('BACK')
    expect(backButton).toBeDisabled()
  })

  it('step indicator dots have proper styling for current vs inactive', async () => {
    const { container } = renderOnboarding()

    // There should be 4 step indicator dots (one per step)
    const dots = container.querySelectorAll('button[aria-label^="Go to step"]')
    expect(dots).toHaveLength(4)

    // Step 1 dot should be active (bg-crt-green), others inactive (bg-zinc-600)
    expect(dots[0]).toHaveClass('bg-crt-green')
    expect(dots[1]).toHaveClass('bg-zinc-600')
    expect(dots[2]).toHaveClass('bg-zinc-600')
    expect(dots[3]).toHaveClass('bg-zinc-600')

    // Advance to step 2 and verify dot styling updates
    await act(async () => { fireEvent.click(screen.getByText('NEXT')) })

    const updatedDots = container.querySelectorAll('button[aria-label^="Go to step"]')
    expect(updatedDots[0]).toHaveClass('bg-zinc-600')
    expect(updatedDots[1]).toHaveClass('bg-crt-green')
    expect(updatedDots[2]).toHaveClass('bg-zinc-600')
    expect(updatedDots[3]).toHaveClass('bg-zinc-600')
  })
})
