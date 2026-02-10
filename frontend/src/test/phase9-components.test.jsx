import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'
import { ToastProvider, useToast } from '../components/Toast'
import ShortcutCheatsheet from '../components/ShortcutCheatsheet'
import OnboardingModal from '../components/OnboardingModal'
import { KEYBOARD_SHORTCUTS, DEFAULT_TEMPLATE_PRESETS } from '../lib/constants'

// Mock localStorage
const localStorageMock = (() => {
  let store = {}
  return {
    getItem: vi.fn((key) => store[key] ?? null),
    setItem: vi.fn((key, value) => { store[key] = String(value) }),
    removeItem: vi.fn((key) => { delete store[key] }),
    clear: () => { store = {} },
  }
})()
Object.defineProperty(window, 'localStorage', { value: localStorageMock })

// Mock hooks for SettingsPanel
vi.mock('../hooks/useTheme.jsx', () => ({
  useTheme: () => ({ theme: 'dark', toggleTheme: vi.fn() }),
  ThemeProvider: ({ children }) => children,
}))

vi.mock('../hooks/useHealthCheck', () => ({
  useHealthCheck: () => ({ status: 'healthy', latency: 42 }),
}))

vi.mock('../hooks/useNotifications', () => ({
  useNotifications: () => ({
    permission: 'default',
    enabled: false,
    setEnabled: vi.fn(),
    requestPermission: vi.fn(() => Promise.resolve('granted')),
    notify: vi.fn(),
  }),
}))

vi.mock('../lib/api', () => ({
  getStoredApiKey: vi.fn(() => null),
  clearApiKey: vi.fn(),
  getTemplates: vi.fn(() => Promise.resolve([])),
  createTemplate: vi.fn(() => Promise.resolve({ id: 1 })),
}))

import SettingsPanel from '../components/SettingsPanel'
import { getStoredApiKey } from '../lib/api'

// ============================================================
// Toast with Action Button
// ============================================================
describe('Toast with Action Button', () => {
  function TestToastAction() {
    const toast = useToast()
    return (
      <button onClick={() => toast('Failed!', 'error', 4000, { label: 'Retry', onClick: vi.fn() })}>
        Trigger
      </button>
    )
  }

  it('renders toast with retry action button', async () => {
    render(
      <ToastProvider>
        <TestToastAction />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('Trigger'))

    expect(screen.getByText('Failed!')).toBeInTheDocument()
    expect(screen.getByText('Retry')).toBeInTheDocument()
  })

  it('renders toast without action when not provided', () => {
    function TestToastNoAction() {
      const toast = useToast()
      return <button onClick={() => toast('Info message', 'info')}>Show</button>
    }

    render(
      <ToastProvider>
        <TestToastNoAction />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('Show'))

    expect(screen.getByText('Info message')).toBeInTheDocument()
    expect(screen.queryByText('Retry')).not.toBeInTheDocument()
  })

  it('calls action onClick and dismisses toast', () => {
    const actionFn = vi.fn()

    function TestToastDismiss() {
      const toast = useToast()
      return <button onClick={() => toast('Error', 'error', 10000, { label: 'Fix', onClick: actionFn })}>Go</button>
    }

    render(
      <ToastProvider>
        <TestToastDismiss />
      </ToastProvider>
    )

    fireEvent.click(screen.getByText('Go'))
    expect(screen.getByText('Fix')).toBeInTheDocument()

    fireEvent.click(screen.getByText('Fix'))
    expect(actionFn).toHaveBeenCalledTimes(1)
    expect(screen.queryByText('Error')).not.toBeInTheDocument()
  })
})

// ============================================================
// ShortcutCheatsheet
// ============================================================
describe('ShortcutCheatsheet', () => {
  it('renders nothing when closed', () => {
    const { container } = render(<ShortcutCheatsheet open={false} onClose={vi.fn()} />)
    expect(container.innerHTML).toBe('')
  })

  it('renders modal when open', () => {
    render(<ShortcutCheatsheet open={true} onClose={vi.fn()} />)
    expect(screen.getByText('Keyboard Shortcuts')).toBeInTheDocument()
  })

  it('displays all shortcut groups', () => {
    render(<ShortcutCheatsheet open={true} onClose={vi.fn()} />)
    const groups = [...new Set(KEYBOARD_SHORTCUTS.map((s) => s.group))]
    groups.forEach((group) => {
      expect(screen.getByText(group)).toBeInTheDocument()
    })
  })

  it('displays all shortcut descriptions', () => {
    render(<ShortcutCheatsheet open={true} onClose={vi.fn()} />)
    KEYBOARD_SHORTCUTS.forEach((s) => {
      expect(screen.getByText(s.description)).toBeInTheDocument()
    })
  })

  it('has dialog role and aria-modal', () => {
    render(<ShortcutCheatsheet open={true} onClose={vi.fn()} />)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('calls onClose when Close button clicked', () => {
    const onClose = vi.fn()
    render(<ShortcutCheatsheet open={true} onClose={onClose} />)
    fireEvent.click(screen.getByText('Close'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when backdrop clicked', () => {
    const onClose = vi.fn()
    render(<ShortcutCheatsheet open={true} onClose={onClose} />)
    // Click the outer overlay (first child is backdrop)
    const overlay = screen.getByRole('dialog').parentElement
    fireEvent.click(overlay)
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('renders kbd elements for keys', () => {
    render(<ShortcutCheatsheet open={true} onClose={vi.fn()} />)
    const kbds = document.querySelectorAll('kbd')
    expect(kbds.length).toBeGreaterThan(0)
  })
})

// ============================================================
// OnboardingModal
// ============================================================
describe('OnboardingModal', () => {
  beforeEach(() => {
    localStorageMock.clear()
  })

  it('renders nothing when closed', () => {
    const { container } = render(<OnboardingModal open={false} onClose={vi.fn()} />)
    expect(container.innerHTML).toBe('')
  })

  it('shows first step when open', () => {
    render(<OnboardingModal open={true} onClose={vi.fn()} />)
    expect(screen.getByText('Welcome to Latent Underground')).toBeInTheDocument()
  })

  it('navigates through steps with Next button', () => {
    render(<OnboardingModal open={true} onClose={vi.fn()} />)

    expect(screen.getByText('Welcome to Latent Underground')).toBeInTheDocument()

    fireEvent.click(screen.getByText('NEXT'))
    expect(screen.getByText('Create Your First Project')).toBeInTheDocument()

    fireEvent.click(screen.getByText('NEXT'))
    expect(screen.getByText('Launch & Monitor')).toBeInTheDocument()
    expect(screen.getByText('GET STARTED')).toBeInTheDocument()
  })

  it('navigates back with Back button', () => {
    render(<OnboardingModal open={true} onClose={vi.fn()} />)

    fireEvent.click(screen.getByText('NEXT'))
    expect(screen.getByText('Create Your First Project')).toBeInTheDocument()

    fireEvent.click(screen.getByText('BACK'))
    expect(screen.getByText('Welcome to Latent Underground')).toBeInTheDocument()
  })

  it('Back button disabled on first step', () => {
    render(<OnboardingModal open={true} onClose={vi.fn()} />)
    expect(screen.getByText('BACK')).toBeDisabled()
  })

  it('sets localStorage and calls onClose on Get Started', () => {
    const onClose = vi.fn()
    render(<OnboardingModal open={true} onClose={onClose} />)

    fireEvent.click(screen.getByText('NEXT'))
    fireEvent.click(screen.getByText('NEXT'))
    fireEvent.click(screen.getByText('GET STARTED'))

    expect(localStorageMock.setItem).toHaveBeenCalledWith('lu_onboarding_complete', 'true')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('sets localStorage and calls onClose on Skip', () => {
    const onClose = vi.fn()
    render(<OnboardingModal open={true} onClose={onClose} />)

    fireEvent.click(screen.getByLabelText('Skip onboarding'))

    expect(localStorageMock.setItem).toHaveBeenCalledWith('lu_onboarding_complete', 'true')
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('has dialog role and aria attributes', () => {
    render(<OnboardingModal open={true} onClose={vi.fn()} />)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
    expect(dialog).toHaveAttribute('aria-labelledby', 'onboarding-title')
  })

  it('shows step indicator dots', () => {
    render(<OnboardingModal open={true} onClose={vi.fn()} />)
    const dots = document.querySelectorAll('[aria-label^="Step"]')
    expect(dots.length).toBe(3)
  })
})

// ============================================================
// SettingsPanel
// ============================================================
describe('SettingsPanel', () => {
  const defaultProps = {
    open: true,
    onClose: vi.fn(),
    onOpenAuth: vi.fn(),
  }

  function renderSettings(props = {}) {
    return render(
      <ToastProvider>
        <SettingsPanel {...defaultProps} {...props} />
      </ToastProvider>
    )
  }

  beforeEach(() => {
    vi.clearAllMocks()
    getStoredApiKey.mockReturnValue(null)
  })

  it('renders nothing when closed', () => {
    renderSettings({ open: false })
    expect(screen.queryByText('Settings')).not.toBeInTheDocument()
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows Settings title when open', () => {
    renderSettings()
    expect(screen.getByText('Settings')).toBeInTheDocument()
  })

  it('has dialog role and aria-modal', () => {
    renderSettings()
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveAttribute('aria-modal', 'true')
  })

  it('shows all four section headers', () => {
    renderSettings()
    expect(screen.getByText('Appearance')).toBeInTheDocument()
    expect(screen.getByText('Authentication')).toBeInTheDocument()
    expect(screen.getByText('Notifications')).toBeInTheDocument()
    expect(screen.getByText('System Info')).toBeInTheDocument()
  })

  it('shows theme as dark', () => {
    renderSettings()
    expect(screen.getByText('dark')).toBeInTheDocument()
  })

  it('shows API key as Not set', () => {
    renderSettings()
    expect(screen.getByText('Not set')).toBeInTheDocument()
  })

  it('shows API key as Configured when present', () => {
    getStoredApiKey.mockReturnValue('test-key')
    renderSettings()
    expect(screen.getByText('Configured')).toBeInTheDocument()
  })

  it('calls onOpenAuth when Change Key clicked', () => {
    const onOpenAuth = vi.fn()
    renderSettings({ onOpenAuth })
    fireEvent.click(screen.getByText('Change Key'))
    expect(onOpenAuth).toHaveBeenCalledTimes(1)
  })

  it('calls onClose when Close button clicked', () => {
    const onClose = vi.fn()
    renderSettings({ onClose })
    fireEvent.click(screen.getByLabelText('Close settings'))
    expect(onClose).toHaveBeenCalledTimes(1)
  })

  it('shows server status', () => {
    renderSettings()
    expect(screen.getByText('Healthy')).toBeInTheDocument()
    expect(screen.getByText('(42ms)')).toBeInTheDocument()
  })

  it('shows rate limit', () => {
    renderSettings()
    expect(screen.getByText('30 req/min')).toBeInTheDocument()
  })

  it('shows version', () => {
    renderSettings()
    expect(screen.getByText(/Latent Underground v\d+\.\d+/)).toBeInTheDocument()
  })
})

// ============================================================
// Constants
// ============================================================
describe('Constants', () => {
  it('KEYBOARD_SHORTCUTS has required fields', () => {
    KEYBOARD_SHORTCUTS.forEach((s) => {
      expect(s).toHaveProperty('keys')
      expect(s).toHaveProperty('description')
      expect(s).toHaveProperty('group')
    })
  })

  it('KEYBOARD_SHORTCUTS has at least 5 shortcuts', () => {
    expect(KEYBOARD_SHORTCUTS.length).toBeGreaterThanOrEqual(5)
  })

  it('DEFAULT_TEMPLATE_PRESETS has 4 presets', () => {
    expect(DEFAULT_TEMPLATE_PRESETS.length).toBe(4)
  })

  it('each preset has name, description, and config', () => {
    DEFAULT_TEMPLATE_PRESETS.forEach((p) => {
      expect(p).toHaveProperty('name')
      expect(p).toHaveProperty('description')
      expect(p).toHaveProperty('config')
      expect(p.config).toHaveProperty('agent_count')
      expect(p.config).toHaveProperty('max_phases')
    })
  })

  it('preset names are unique', () => {
    const names = DEFAULT_TEMPLATE_PRESETS.map((p) => p.name)
    expect(new Set(names).size).toBe(names.length)
  })
})
