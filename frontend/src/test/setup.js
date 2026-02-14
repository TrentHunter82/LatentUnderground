import '@testing-library/jest-dom'
import { afterEach } from 'vitest'

// Clear localStorage between tests to prevent filter/state leaks
afterEach(() => {
  localStorage.clear()
})


// JSDOM doesn't implement scrollIntoView or scrollTo
Element.prototype.scrollIntoView = () => {}
if (!Element.prototype.scrollTo) {
  Element.prototype.scrollTo = function (opts) {
    if (typeof opts === 'object') {
      this.scrollTop = opts.top || 0
      this.scrollLeft = opts.left || 0
    }
  }
}

// Mock getBoundingClientRect for virtual scroll support
// TanStack Virtual needs non-zero dimensions on the scroll container
const originalGetBCR = Element.prototype.getBoundingClientRect
Element.prototype.getBoundingClientRect = function () {
  const rect = originalGetBCR.call(this)
  // If the element has no height (jsdom default), return a reasonable mock
  if (rect.height === 0 && rect.width === 0) {
    return { top: 0, left: 0, bottom: 600, right: 800, width: 800, height: 600, x: 0, y: 0, toJSON: () => {} }
  }
  return rect
}

// JSDOM doesn't implement ResizeObserver - provide a functional mock
// TanStack Virtual uses ResizeObserver to measure the scroll container
// IMPORTANT: Callback must be deferred (setTimeout) to avoid infinite recursion.
// TanStack Virtual's measureElement calls observe(), and a synchronous callback
// triggers _measureElement again, which calls observe() → stack overflow.
class MockResizeObserver {
  constructor(cb) {
    this._cb = cb
    this._disconnected = false
  }
  observe(target) {
    // Defer callback to break the observe → callback → measureElement → observe cycle
    setTimeout(() => {
      if (!this._disconnected) {
        this._cb?.([{
          target,
          contentRect: { top: 0, left: 0, bottom: 600, right: 800, width: 800, height: 600, x: 0, y: 0 },
          borderBoxSize: [{ blockSize: 600, inlineSize: 800 }],
          contentBoxSize: [{ blockSize: 600, inlineSize: 800 }],
        }])
      }
    }, 0)
  }
  unobserve() {}
  disconnect() { this._disconnected = true }
}
globalThis.ResizeObserver = MockResizeObserver
window.ResizeObserver = MockResizeObserver

// Suppress TanStack Virtual's post-unmount errors in jsdom.
// After unmount, TanStack Virtual's scheduled rAF fires and tries to access
// this.targetWindow.requestAnimationFrame where targetWindow is already null.
// This is a known TanStack/jsdom interaction issue and is harmless.
window.addEventListener('error', (event) => {
  if (event.error?.message?.includes('requestAnimationFrame')) {
    event.preventDefault()
    event.stopImmediatePropagation()
  }
})

// JSDOM doesn't implement matchMedia - provide a mock for theme detection
window.matchMedia = window.matchMedia || function (query) {
  return {
    matches: false,
    media: query,
    onchange: null,
    addListener: function () {},
    removeListener: function () {},
    addEventListener: function () {},
    removeEventListener: function () {},
    dispatchEvent: function () { return false },
  }
}
