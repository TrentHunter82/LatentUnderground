import { useEffect, useRef, useCallback, useState } from 'react'

const BACKOFF_BASE = 1000
const BACKOFF_MAX = 30000
const MAX_RETRIES = 15
const JITTER_FACTOR = 0.2

export function useWebSocket(onMessage) {
  const wsRef = useRef(null)
  const [connected, setConnected] = useState(false)
  const reconnectTimer = useRef(null)
  const onMessageRef = useRef(onMessage)
  const retriesRef = useRef(0)
  onMessageRef.current = onMessage

  const getBackoffDelay = useCallback(() => {
    const base = Math.min(BACKOFF_BASE * Math.pow(2, retriesRef.current), BACKOFF_MAX)
    const jitter = base * JITTER_FACTOR * (Math.random() * 2 - 1)
    return Math.max(0, base + jitter)
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    if (retriesRef.current >= MAX_RETRIES) return

    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const ws = new WebSocket(`${protocol}//${window.location.host}/ws`)

    ws.onopen = () => {
      setConnected(true)
      retriesRef.current = 0
      if (reconnectTimer.current) {
        clearTimeout(reconnectTimer.current)
        reconnectTimer.current = null
      }
    }

    ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data)
        onMessageRef.current?.(data)
      } catch {}
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)

      if (retriesRef.current < MAX_RETRIES) {
        const delay = getBackoffDelay()
        retriesRef.current++
        reconnectTimer.current = setTimeout(connect, delay)
      }
    }

    ws.onerror = () => ws.close()
    wsRef.current = ws
  }, [getBackoffDelay])

  useEffect(() => {
    connect()
    return () => {
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const send = useCallback((data) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof data === 'string' ? data : JSON.stringify(data))
    }
  }, [])

  return { connected, send }
}
