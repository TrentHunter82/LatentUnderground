import { describe, it, expect, vi, beforeEach } from 'vitest'

// Test the raw API functions by mocking fetch directly
const mockFetch = vi.fn()
global.fetch = mockFetch

function jsonResponse(data, status = 200) {
  return Promise.resolve({
    ok: status >= 200 && status < 300,
    status,
    statusText: 'OK',
    json: () => Promise.resolve(data),
    text: () => Promise.resolve(JSON.stringify(data)),
  })
}

describe('sendSwarmInput API', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    localStorage.clear()
  })

  it('sends POST with project_id and text', async () => {
    mockFetch.mockReturnValue(jsonResponse({ status: 'sent', project_id: 1 }))

    // Dynamic import to get fresh module
    vi.resetModules()
    const { sendSwarmInput } = await import('../lib/api')
    const result = await sendSwarmInput(1, 'hello')

    expect(result).toEqual({ status: 'sent', project_id: 1 })
    expect(mockFetch).toHaveBeenCalledWith(
      '/api/swarm/input',
      expect.objectContaining({
        method: 'POST',
        body: JSON.stringify({ project_id: 1, text: 'hello', agent: null }),
      })
    )
  })

  it('attaches Bearer header when API key stored', async () => {
    localStorage.setItem('lu_api_key', 'my-key')
    mockFetch.mockReturnValue(jsonResponse({ status: 'sent' }))

    vi.resetModules()
    const { sendSwarmInput } = await import('../lib/api')
    await sendSwarmInput(1, 'test')

    const [, options] = mockFetch.mock.calls[0]
    expect(options.headers.Authorization).toBe('Bearer my-key')
  })

  it('dispatches auth-required on 401', async () => {
    mockFetch.mockReturnValue(jsonResponse({ detail: 'Unauthorized' }, 401))

    const dispatchSpy = vi.spyOn(window, 'dispatchEvent')
    vi.resetModules()
    const { sendSwarmInput } = await import('../lib/api')

    await expect(sendSwarmInput(1, 'test')).rejects.toThrow('Authentication required')
    expect(dispatchSpy).toHaveBeenCalledWith(
      expect.objectContaining({ type: 'auth-required' })
    )
    dispatchSpy.mockRestore()
  })
})

describe('searchLogs API', () => {
  beforeEach(() => {
    mockFetch.mockReset()
    localStorage.clear()
  })

  it('includes from_date and to_date in URL params', async () => {
    mockFetch.mockReturnValue(jsonResponse({ results: [], total: 0 }))

    vi.resetModules()
    const { searchLogs } = await import('../lib/api')
    await searchLogs(1, { q: 'error', from_date: '2026-01-01', to_date: '2026-02-01' })

    const url = mockFetch.mock.calls[0][0]
    expect(url).toContain('project_id=1')
    expect(url).toContain('q=error')
    expect(url).toContain('from_date=2026-01-01')
    expect(url).toContain('to_date=2026-02-01')
  })

  it('omits undefined filter params', async () => {
    mockFetch.mockReturnValue(jsonResponse({ results: [], total: 0 }))

    vi.resetModules()
    const { searchLogs } = await import('../lib/api')
    await searchLogs(1, {})

    const url = mockFetch.mock.calls[0][0]
    expect(url).toContain('project_id=1')
    expect(url).not.toContain('from_date')
    expect(url).not.toContain('to_date')
    expect(url).not.toContain('q=')
  })
})

describe('Auth helpers', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('setApiKey stores key in localStorage', async () => {
    vi.resetModules()
    const { setApiKey, getStoredApiKey } = await import('../lib/api')
    setApiKey('test-key-123')
    expect(getStoredApiKey()).toBe('test-key-123')
  })

  it('clearApiKey removes key from localStorage', async () => {
    vi.resetModules()
    const { setApiKey, clearApiKey, getStoredApiKey } = await import('../lib/api')
    setApiKey('test-key')
    clearApiKey()
    expect(getStoredApiKey()).toBeNull()
  })

  it('setApiKey with empty string removes key', async () => {
    vi.resetModules()
    const { setApiKey, getStoredApiKey } = await import('../lib/api')
    setApiKey('test-key')
    setApiKey('')
    expect(getStoredApiKey()).toBeNull()
  })
})
