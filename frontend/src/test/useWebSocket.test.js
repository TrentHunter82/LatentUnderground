import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useWebSocket } from '../hooks/useWebSocket'

// Mock WebSocket
class MockWebSocket {
  static OPEN = 1
  static CLOSED = 3
  static instances = []
  static autoOpen = true

  constructor(url) {
    this.url = url
    this.readyState = MockWebSocket.OPEN
    this.onopen = null
    this.onclose = null
    this.onmessage = null
    this.onerror = null
    this.sent = []
    MockWebSocket.instances.push(this)

    // Auto-trigger onopen unless disabled
    if (MockWebSocket.autoOpen) {
      setTimeout(() => this.onopen?.(), 0)
    }
  }

  send(data) {
    this.sent.push(data)
  }

  close() {
    this.readyState = MockWebSocket.CLOSED
    this.onclose?.()
  }
}

beforeEach(() => {
  MockWebSocket.instances = []
  MockWebSocket.autoOpen = true
  global.WebSocket = MockWebSocket
  vi.useFakeTimers()
})

afterEach(() => {
  vi.useRealTimers()
  delete global.WebSocket
})

describe('useWebSocket', () => {
  it('connects on mount', async () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket(onMessage))

    expect(MockWebSocket.instances).toHaveLength(1)
    expect(MockWebSocket.instances[0].url).toContain('/ws')
  })

  it('sets connected to true after onopen', async () => {
    const onMessage = vi.fn()
    const { result } = renderHook(() => useWebSocket(onMessage))

    // Initially not connected (onopen hasn't fired yet)
    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    expect(result.current.connected).toBe(true)
  })

  it('parses incoming JSON messages', async () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.onmessage({ data: JSON.stringify({ type: 'heartbeat', agent: 'Claude-1' }) })
    })

    expect(onMessage).toHaveBeenCalledWith({ type: 'heartbeat', agent: 'Claude-1' })
  })

  it('ignores invalid JSON messages', async () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    const ws = MockWebSocket.instances[0]
    act(() => {
      ws.onmessage({ data: 'not json' })
    })

    expect(onMessage).not.toHaveBeenCalled()
  })

  it('sends data via send function', async () => {
    const onMessage = vi.fn()
    const { result } = renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    act(() => {
      result.current.send({ type: 'ping' })
    })

    expect(MockWebSocket.instances[0].sent).toEqual([JSON.stringify({ type: 'ping' })])
  })

  it('sends string data directly', async () => {
    const onMessage = vi.fn()
    const { result } = renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    act(() => {
      result.current.send('ping')
    })

    expect(MockWebSocket.instances[0].sent).toEqual(['ping'])
  })

  it('attempts reconnect after disconnect with backoff', async () => {
    const onMessage = vi.fn()
    const { result } = renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    expect(MockWebSocket.instances).toHaveLength(1)

    // Simulate disconnect
    act(() => {
      MockWebSocket.instances[0].close()
    })

    expect(result.current.connected).toBe(false)

    // First retry: base 1s * 2^0 = 1s, plus up to 20% jitter = max 1.2s
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1300)
    })

    // Should have created a new WebSocket instance
    expect(MockWebSocket.instances).toHaveLength(2)
  })

  it('uses exponential backoff on consecutive failures', async () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    // Disable auto-open BEFORE triggering disconnect so reconnected sockets
    // don't auto-fire onopen (simulating server being down)
    MockWebSocket.autoOpen = false

    // First disconnect -> retry scheduled at ~1s (base * 2^0)
    act(() => { MockWebSocket.instances[0].close() })
    await act(async () => { await vi.advanceTimersByTimeAsync(1300) })
    expect(MockWebSocket.instances).toHaveLength(2)

    // Second socket never opened (server still down), close it
    act(() => { MockWebSocket.instances[1].close() })

    // Second retry: base * 2^1 = 2s. Should NOT reconnect after just 1.3s
    await act(async () => { await vi.advanceTimersByTimeAsync(1300) })
    expect(MockWebSocket.instances).toHaveLength(2)
    // But should after enough time (2.5s total covers 2s + 20% jitter)
    await act(async () => { await vi.advanceTimersByTimeAsync(1200) })
    expect(MockWebSocket.instances).toHaveLength(3)
  })

  it('resets backoff on successful connection', async () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    // Disconnect and reconnect
    act(() => { MockWebSocket.instances[0].close() })
    await act(async () => { await vi.advanceTimersByTimeAsync(1300) })
    expect(MockWebSocket.instances).toHaveLength(2)

    // Simulate successful connection (onopen auto-fires)
    await act(async () => { await vi.advanceTimersByTimeAsync(10) })

    // Disconnect again -> should use base delay (~1s) not doubled
    act(() => { MockWebSocket.instances[1].close() })
    await act(async () => { await vi.advanceTimersByTimeAsync(1300) })
    expect(MockWebSocket.instances).toHaveLength(3)
  })

  it('gives up after max retries', async () => {
    const onMessage = vi.fn()
    renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    // Disable auto-open so reconnected sockets simulate failed connections
    MockWebSocket.autoOpen = false

    // Simulate 15 consecutive failures (max retries)
    // First close is from the successfully opened initial socket
    act(() => { MockWebSocket.instances[0].close() })

    for (let i = 0; i < 15; i++) {
      // Advance enough time for any backoff (max 30s + jitter)
      await act(async () => { await vi.advanceTimersByTimeAsync(40000) })
      const lastIdx = MockWebSocket.instances.length - 1
      // Close the reconnected socket (it never opened successfully)
      act(() => { MockWebSocket.instances[lastIdx].close() })
    }

    const countAfterMaxRetries = MockWebSocket.instances.length
    // Advance time - should NOT create any more instances
    await act(async () => { await vi.advanceTimersByTimeAsync(40000) })
    expect(MockWebSocket.instances).toHaveLength(countAfterMaxRetries)
  })

  it('cleans up on unmount', async () => {
    const onMessage = vi.fn()
    const { unmount } = renderHook(() => useWebSocket(onMessage))

    await act(async () => {
      await vi.advanceTimersByTimeAsync(10)
    })

    const ws = MockWebSocket.instances[0]
    unmount()

    expect(ws.readyState).toBe(MockWebSocket.CLOSED)
  })
})
