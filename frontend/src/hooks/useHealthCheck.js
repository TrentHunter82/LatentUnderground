import { useState, useEffect, useRef, useCallback } from 'react'

const POLL_INTERVAL = 30000
const SLOW_THRESHOLD = 2000

export function useHealthCheck() {
  const [status, setStatus] = useState('disconnected')
  const [latency, setLatency] = useState(null)
  const timerRef = useRef(null)

  const check = useCallback(async () => {
    const start = performance.now()
    try {
      const res = await fetch('/api/health')
      const elapsed = Math.round(performance.now() - start)
      setLatency(elapsed)
      if (!res.ok) {
        setStatus('degraded')
      } else if (elapsed > SLOW_THRESHOLD) {
        setStatus('slow')
      } else {
        setStatus('healthy')
      }
    } catch {
      setStatus('disconnected')
      setLatency(null)
    }
  }, [])

  useEffect(() => {
    check()
    timerRef.current = setInterval(check, POLL_INTERVAL)
    return () => clearInterval(timerRef.current)
  }, [check])

  return { status, latency }
}
