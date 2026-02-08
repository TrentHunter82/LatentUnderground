import { useState, useEffect, useCallback } from 'react'

const STORAGE_KEY = 'latent-notifications-enabled'

export function useNotifications() {
  const [permission, setPermission] = useState(() => {
    if (typeof Notification === 'undefined') return 'denied'
    return Notification.permission
  })

  const [enabled, setEnabled] = useState(() => {
    try {
      return localStorage.getItem(STORAGE_KEY) === 'true'
    } catch {
      return false
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, String(enabled))
    } catch {}
  }, [enabled])

  const requestPermission = useCallback(async () => {
    if (typeof Notification === 'undefined') return 'denied'
    if (Notification.permission === 'granted') {
      setPermission('granted')
      setEnabled(true)
      return 'granted'
    }
    try {
      const result = await Notification.requestPermission()
      setPermission(result)
      if (result === 'granted') setEnabled(true)
      return result
    } catch {
      return 'denied'
    }
  }, [])

  const notify = useCallback((title, options = {}) => {
    if (!enabled) return
    if (typeof Notification === 'undefined') return
    if (Notification.permission !== 'granted') return
    if (document.hasFocus()) return
    try {
      new Notification(title, options)
    } catch {}
  }, [enabled])

  return { permission, enabled, setEnabled, requestPermission, notify }
}
