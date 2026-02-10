import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, act, waitFor } from '@testing-library/react'

// Mock api module at top level
vi.mock('../lib/api', () => ({
  getWebhooks: vi.fn(),
  createWebhook: vi.fn(),
  updateWebhook: vi.fn(),
  deleteWebhook: vi.fn(),
}))

import { getWebhooks, createWebhook, updateWebhook, deleteWebhook } from '../lib/api'
import { ToastProvider } from '../components/Toast'
import WebhookManager from '../components/WebhookManager'

function renderManager(props = {}) {
  return render(
    <ToastProvider>
      <WebhookManager projectId={1} {...props} />
    </ToastProvider>
  )
}

const sampleWebhooks = [
  {
    id: 10,
    url: 'https://example.com/hook1',
    events: ['swarm_launched', 'swarm_stopped'],
    enabled: true,
    has_secret: false,
    project_id: 1,
  },
  {
    id: 11,
    url: 'https://example.com/hook2',
    events: ['swarm_crashed'],
    enabled: false,
    has_secret: true,
    project_id: 1,
  },
  {
    id: 12,
    url: 'https://global.example.com/hook',
    events: ['swarm_error'],
    enabled: true,
    has_secret: false,
    project_id: null,
  },
  {
    id: 13,
    url: 'https://other-project.com/hook',
    events: ['swarm_launched'],
    enabled: true,
    has_secret: false,
    project_id: 99,
  },
]

describe('WebhookManager', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // --- 1. Loading state ---
  it('shows loading state initially', () => {
    // Never-resolving promise to keep component in loading state
    getWebhooks.mockImplementation(() => new Promise(() => {}))

    renderManager()

    expect(screen.getByText('Loading webhooks...')).toBeInTheDocument()
  })

  // --- 2. Empty state ---
  it('shows empty state when no webhooks match', async () => {
    getWebhooks.mockResolvedValue([])

    await act(async () => {
      renderManager()
    })

    expect(screen.getByText('No webhooks configured')).toBeInTheDocument()
    expect(screen.queryByText('Loading webhooks...')).not.toBeInTheDocument()
  })

  // --- 3. Renders webhook list with url, events, LED indicators ---
  it('renders webhook list with url, events, and LED indicators', async () => {
    getWebhooks.mockResolvedValue(sampleWebhooks)

    await act(async () => {
      renderManager()
    })

    // URLs for projectId=1 and global (null) should be visible
    expect(screen.getByText('https://example.com/hook1')).toBeInTheDocument()
    expect(screen.getByText('https://example.com/hook2')).toBeInTheDocument()
    expect(screen.getByText('https://global.example.com/hook')).toBeInTheDocument()

    // Events as tag labels
    expect(screen.getByText('swarm_launched')).toBeInTheDocument()
    expect(screen.getByText('swarm_stopped')).toBeInTheDocument()
    expect(screen.getByText('swarm_crashed')).toBeInTheDocument()
    expect(screen.getByText('swarm_error')).toBeInTheDocument()

    // LED indicators - enabled webhook shows "Enabled", disabled shows "Disabled"
    const enabledIndicators = screen.getAllByLabelText('Enabled')
    const disabledIndicators = screen.getAllByLabelText('Disabled')
    expect(enabledIndicators.length).toBe(2) // hook1 and global
    expect(disabledIndicators.length).toBe(1) // hook2
  })

  // --- 4. Shows [signed] badge when has_secret=true ---
  it('shows [signed] badge when has_secret is true', async () => {
    getWebhooks.mockResolvedValue(sampleWebhooks)

    await act(async () => {
      renderManager()
    })

    expect(screen.getByText('[signed]')).toBeInTheDocument()
    expect(screen.getByTitle('Has HMAC secret configured')).toBeInTheDocument()
  })

  // --- 5. Shows [global] badge when project_id is null ---
  it('shows [global] badge when project_id is null', async () => {
    getWebhooks.mockResolvedValue(sampleWebhooks)

    await act(async () => {
      renderManager()
    })

    expect(screen.getByText('[global]')).toBeInTheDocument()
    expect(screen.getByTitle('Global webhook (not project-specific)')).toBeInTheDocument()
  })

  // --- 6. Filters webhooks to match projectId or null ---
  it('filters webhooks to match projectId or null (global)', async () => {
    getWebhooks.mockResolvedValue(sampleWebhooks)

    await act(async () => {
      renderManager({ projectId: 1 })
    })

    // Should show project_id=1 and project_id=null webhooks
    expect(screen.getByText('https://example.com/hook1')).toBeInTheDocument()
    expect(screen.getByText('https://example.com/hook2')).toBeInTheDocument()
    expect(screen.getByText('https://global.example.com/hook')).toBeInTheDocument()

    // Should NOT show project_id=99 webhook
    expect(screen.queryByText('https://other-project.com/hook')).not.toBeInTheDocument()
  })

  // --- 7. "+ New" button opens form, Cancel closes it ---
  it('opens form on "+ New" and closes on Cancel', async () => {
    getWebhooks.mockResolvedValue([])

    await act(async () => {
      renderManager()
    })

    // Click "+ New"
    fireEvent.click(screen.getByLabelText('Add new webhook'))

    expect(screen.getByText('New Webhook')).toBeInTheDocument()
    // "+ New" button is conditionally hidden when form is open
    expect(screen.queryByLabelText('Add new webhook')).not.toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /url/i })).toBeInTheDocument()

    // Cancel closes form
    fireEvent.click(screen.getByText('Cancel'))

    expect(screen.queryByText('New Webhook')).not.toBeInTheDocument()
    expect(screen.getByLabelText('Add new webhook')).toBeInTheDocument()
  })

  // --- 8. Toggles event buttons (aria-pressed changes) ---
  it('toggles event buttons and updates aria-pressed', async () => {
    getWebhooks.mockResolvedValue([])

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))

    const launchedBtn = screen.getByLabelText('Toggle swarm_launched event')
    const stoppedBtn = screen.getByLabelText('Toggle swarm_stopped event')

    // Initially no events selected
    expect(launchedBtn).toHaveAttribute('aria-pressed', 'false')
    expect(stoppedBtn).toHaveAttribute('aria-pressed', 'false')

    // Select swarm_launched
    fireEvent.click(launchedBtn)
    expect(launchedBtn).toHaveAttribute('aria-pressed', 'true')

    // Select swarm_stopped
    fireEvent.click(stoppedBtn)
    expect(stoppedBtn).toHaveAttribute('aria-pressed', 'true')

    // Deselect swarm_launched
    fireEvent.click(launchedBtn)
    expect(launchedBtn).toHaveAttribute('aria-pressed', 'false')
    expect(stoppedBtn).toHaveAttribute('aria-pressed', 'true')
  })

  // --- 9. Submit creates webhook with correct payload ---
  it('creates webhook with correct payload on submit', async () => {
    getWebhooks.mockResolvedValueOnce([])
    createWebhook.mockResolvedValue({ id: 20, url: 'https://new.example.com/hook' })
    getWebhooks.mockResolvedValueOnce([])

    await act(async () => {
      renderManager({ projectId: 5 })
    })

    // Open form
    fireEvent.click(screen.getByLabelText('Add new webhook'))

    // Fill URL
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://new.example.com/hook' },
    })

    // Select events
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))
    fireEvent.click(screen.getByLabelText('Toggle swarm_error event'))

    // Fill secret
    fireEvent.change(document.getElementById('webhook-secret'), {
      target: { value: 'my-secret-key' },
    })

    // Submit
    await act(async () => {
      fireEvent.click(screen.getByText('Create'))
    })

    expect(createWebhook).toHaveBeenCalledWith({
      url: 'https://new.example.com/hook',
      events: ['swarm_launched', 'swarm_error'],
      project_id: 5,
      secret: 'my-secret-key',
    })
  })

  // --- 10. Edit pre-fills form, submit updates webhook ---
  it('edits a webhook: pre-fills form and submits update', async () => {
    const webhook = {
      id: 10,
      url: 'https://example.com/hook1',
      events: ['swarm_launched', 'swarm_stopped'],
      enabled: true,
      has_secret: true,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([webhook])
    updateWebhook.mockResolvedValue({ ...webhook, url: 'https://updated.com/hook' })
    getWebhooks.mockResolvedValueOnce([{ ...webhook, url: 'https://updated.com/hook' }])

    await act(async () => {
      renderManager()
    })

    // Click edit button
    fireEvent.click(screen.getByLabelText('Edit https://example.com/hook1'))

    // Verify form is pre-filled
    expect(screen.getByText('Edit Webhook')).toBeInTheDocument()
    expect(screen.getByRole('textbox', { name: /url/i })).toHaveValue('https://example.com/hook1')

    // Events should be pre-selected
    expect(screen.getByLabelText('Toggle swarm_launched event')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Toggle swarm_stopped event')).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('Toggle swarm_crashed event')).toHaveAttribute('aria-pressed', 'false')

    // Secret should be blank (not pre-filled)
    expect(document.getElementById('webhook-secret')).toHaveValue('')

    // Update URL
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://updated.com/hook' },
    })

    // Submit update
    await act(async () => {
      fireEvent.click(screen.getByText('Update'))
    })

    expect(updateWebhook).toHaveBeenCalledWith(10, {
      url: 'https://updated.com/hook',
      events: ['swarm_launched', 'swarm_stopped'],
    })
  })

  // --- 11. Delete shows ConfirmDialog, confirm deletes ---
  it('deletes a webhook after confirming in ConfirmDialog', async () => {
    const webhook = {
      id: 10,
      url: 'https://example.com/hook1',
      events: ['swarm_launched'],
      enabled: true,
      has_secret: false,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([webhook])
    deleteWebhook.mockResolvedValue(null)
    getWebhooks.mockResolvedValueOnce([])

    await act(async () => {
      renderManager()
    })

    // Click delete button
    fireEvent.click(screen.getByLabelText('Delete https://example.com/hook1'))

    // ConfirmDialog should be open
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()
    expect(screen.getByText('Delete Webhook')).toBeInTheDocument()
    expect(screen.getByText(/Delete webhook for "https:\/\/example\.com\/hook1"\? This cannot be undone\./)).toBeInTheDocument()

    // Confirm deletion
    await act(async () => {
      fireEvent.click(screen.getByText('Delete'))
    })

    expect(deleteWebhook).toHaveBeenCalledWith(10)
  })

  // --- 12. Toggle enable/disable calls updateWebhook ---
  it('toggles enable/disable via updateWebhook', async () => {
    const enabledWebhook = {
      id: 10,
      url: 'https://example.com/enabled',
      events: ['swarm_launched'],
      enabled: true,
      has_secret: false,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([enabledWebhook])
    updateWebhook.mockResolvedValue({ ...enabledWebhook, enabled: false })
    getWebhooks.mockResolvedValueOnce([{ ...enabledWebhook, enabled: false }])

    await act(async () => {
      renderManager()
    })

    // Click disable button (webhook is currently enabled)
    await act(async () => {
      fireEvent.click(screen.getByLabelText('Disable https://example.com/enabled'))
    })

    expect(updateWebhook).toHaveBeenCalledWith(10, { enabled: false })
  })

  // --- 13. Form validation: submit disabled without url or events ---
  it('disables submit button when url is empty or no events selected', async () => {
    getWebhooks.mockResolvedValue([])

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))

    const createBtn = screen.getByText('Create')

    // Initially disabled: no url, no events
    expect(createBtn).toBeDisabled()

    // Add URL but no events - still disabled
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://example.com' },
    })
    expect(createBtn).toBeDisabled()

    // Select an event - now enabled
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))
    expect(createBtn).not.toBeDisabled()

    // Clear URL - disabled again
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: '' },
    })
    expect(createBtn).toBeDisabled()
  })

  // --- 14. Error state: shows toast on getWebhooks failure ---
  it('shows error toast when getWebhooks fails', async () => {
    getWebhooks.mockRejectedValue(new Error('Network error'))

    await act(async () => {
      renderManager()
    })

    expect(screen.getByText(/Failed to load webhooks: Network error/)).toBeInTheDocument()
    // Loading state should be cleared
    expect(screen.queryByText('Loading webhooks...')).not.toBeInTheDocument()
  })

  // --- Additional tests for thorough coverage ---

  it('shows "Select at least one event" validation message when no events selected', async () => {
    getWebhooks.mockResolvedValue([])

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))

    expect(screen.getByText('Select at least one event')).toBeInTheDocument()

    // Select an event - message disappears
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))
    expect(screen.queryByText('Select at least one event')).not.toBeInTheDocument()

    // Deselect - message reappears
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))
    expect(screen.getByText('Select at least one event')).toBeInTheDocument()
  })

  it('does not include secret in update payload when left blank', async () => {
    const webhook = {
      id: 10,
      url: 'https://example.com/hook',
      events: ['swarm_launched'],
      enabled: true,
      has_secret: true,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([webhook])
    updateWebhook.mockResolvedValue(webhook)
    getWebhooks.mockResolvedValueOnce([webhook])

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Edit https://example.com/hook'))

    // Submit without touching secret
    await act(async () => {
      fireEvent.click(screen.getByText('Update'))
    })

    // Secret should not be in the payload (blank = keep existing)
    expect(updateWebhook).toHaveBeenCalledWith(10, {
      url: 'https://example.com/hook',
      events: ['swarm_launched'],
    })
    expect(updateWebhook.mock.calls[0][1]).not.toHaveProperty('secret')
  })

  it('shows success toast after creating a webhook', async () => {
    getWebhooks.mockResolvedValueOnce([])
    createWebhook.mockResolvedValue({ id: 20, url: 'https://new.com/hook' })
    getWebhooks.mockResolvedValueOnce([])

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://new.com/hook' },
    })
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))

    await act(async () => {
      fireEvent.click(screen.getByText('Create'))
    })

    expect(screen.getByText('Webhook created')).toBeInTheDocument()
  })

  it('shows error toast when create fails', async () => {
    getWebhooks.mockResolvedValue([])
    createWebhook.mockRejectedValue(new Error('Validation error'))

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://bad.com/hook' },
    })
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))

    await act(async () => {
      fireEvent.click(screen.getByText('Create'))
    })

    expect(screen.getByText(/Save failed: Validation error/)).toBeInTheDocument()
  })

  it('shows success toast after deleting a webhook', async () => {
    const webhook = {
      id: 10,
      url: 'https://example.com/hook',
      events: ['swarm_launched'],
      enabled: true,
      has_secret: false,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([webhook])
    deleteWebhook.mockResolvedValue(null)
    getWebhooks.mockResolvedValueOnce([])

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Delete https://example.com/hook'))

    await act(async () => {
      fireEvent.click(screen.getByText('Delete'))
    })

    expect(screen.getByText('Webhook deleted')).toBeInTheDocument()
  })

  it('shows error toast when toggle fails', async () => {
    const webhook = {
      id: 10,
      url: 'https://example.com/hook',
      events: ['swarm_launched'],
      enabled: true,
      has_secret: false,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([webhook])
    updateWebhook.mockRejectedValue(new Error('Server down'))

    await act(async () => {
      renderManager()
    })

    await act(async () => {
      fireEvent.click(screen.getByLabelText('Disable https://example.com/hook'))
    })

    expect(screen.getByText(/Toggle failed: Server down/)).toBeInTheDocument()
  })

  it('closes form after successful create and refreshes list', async () => {
    const newWebhook = {
      id: 20,
      url: 'https://new.com/hook',
      events: ['swarm_launched'],
      enabled: true,
      has_secret: false,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([])
    createWebhook.mockResolvedValue(newWebhook)
    getWebhooks.mockResolvedValueOnce([newWebhook])

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://new.com/hook' },
    })
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))

    await act(async () => {
      fireEvent.click(screen.getByText('Create'))
    })

    // Form should be closed
    expect(screen.queryByText('New Webhook')).not.toBeInTheDocument()

    // List should show new webhook
    expect(screen.getByText('https://new.com/hook')).toBeInTheDocument()
  })

  it('shows "Saving..." text while saving', async () => {
    getWebhooks.mockResolvedValue([])
    let resolveCreate
    createWebhook.mockImplementation(() => new Promise((r) => { resolveCreate = r }))

    await act(async () => {
      renderManager()
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://slow.com/hook' },
    })
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))

    // Start submit without awaiting
    act(() => {
      fireEvent.click(screen.getByText('Create'))
    })

    await waitFor(() => {
      expect(screen.getByText('Saving...')).toBeInTheDocument()
    })

    // Resolve to clean up
    await act(async () => {
      resolveCreate({ id: 30 })
    })
  })

  it('cancels delete when ConfirmDialog cancel is clicked', async () => {
    const webhook = {
      id: 10,
      url: 'https://example.com/hook',
      events: ['swarm_launched'],
      enabled: true,
      has_secret: false,
      project_id: 1,
    }
    getWebhooks.mockResolvedValue([webhook])

    await act(async () => {
      renderManager()
    })

    // Open delete dialog
    fireEvent.click(screen.getByLabelText('Delete https://example.com/hook'))
    expect(screen.getByRole('alertdialog')).toBeInTheDocument()

    // Click Cancel in the dialog
    fireEvent.click(screen.getByText('Cancel'))

    // Dialog should be closed, webhook not deleted
    expect(screen.queryByRole('alertdialog')).not.toBeInTheDocument()
    expect(deleteWebhook).not.toHaveBeenCalled()
    expect(screen.getByText('https://example.com/hook')).toBeInTheDocument()
  })

  it('shows enable button for disabled webhooks', async () => {
    const webhook = {
      id: 11,
      url: 'https://example.com/disabled',
      events: ['swarm_crashed'],
      enabled: false,
      has_secret: false,
      project_id: 1,
    }
    getWebhooks.mockResolvedValueOnce([webhook])
    updateWebhook.mockResolvedValue({ ...webhook, enabled: true })
    getWebhooks.mockResolvedValueOnce([{ ...webhook, enabled: true }])

    await act(async () => {
      renderManager()
    })

    // Should show "Enable" button for disabled webhook
    const enableBtn = screen.getByLabelText('Enable https://example.com/disabled')
    expect(enableBtn).toBeInTheDocument()

    await act(async () => {
      fireEvent.click(enableBtn)
    })

    expect(updateWebhook).toHaveBeenCalledWith(11, { enabled: true })
  })

  it('includes secret in create payload when provided', async () => {
    getWebhooks.mockResolvedValueOnce([])
    createWebhook.mockResolvedValue({ id: 25 })
    getWebhooks.mockResolvedValueOnce([])

    await act(async () => {
      renderManager({ projectId: 3 })
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://signed.com/hook' },
    })
    fireEvent.click(screen.getByLabelText('Toggle swarm_stopped event'))
    fireEvent.change(document.getElementById('webhook-secret'), {
      target: { value: 'super-secret' },
    })

    await act(async () => {
      fireEvent.click(screen.getByText('Create'))
    })

    expect(createWebhook).toHaveBeenCalledWith({
      url: 'https://signed.com/hook',
      events: ['swarm_stopped'],
      project_id: 3,
      secret: 'super-secret',
    })
  })

  it('does not include secret in create payload when empty', async () => {
    getWebhooks.mockResolvedValueOnce([])
    createWebhook.mockResolvedValue({ id: 26 })
    getWebhooks.mockResolvedValueOnce([])

    await act(async () => {
      renderManager({ projectId: 1 })
    })

    fireEvent.click(screen.getByLabelText('Add new webhook'))
    fireEvent.change(screen.getByRole('textbox', { name: /url/i }), {
      target: { value: 'https://nosecret.com/hook' },
    })
    fireEvent.click(screen.getByLabelText('Toggle swarm_launched event'))

    // Leave secret empty (default)
    await act(async () => {
      fireEvent.click(screen.getByText('Create'))
    })

    const payload = createWebhook.mock.calls[0][0]
    expect(payload).not.toHaveProperty('secret')
    expect(payload).toEqual({
      url: 'https://nosecret.com/hook',
      events: ['swarm_launched'],
      project_id: 1,
    })
  })
})
