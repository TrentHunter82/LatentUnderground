import '@testing-library/jest-dom'

// JSDOM doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {}

// JSDOM doesn't implement ResizeObserver - provide a functional mock
class MockResizeObserver {
  constructor(cb) { this._cb = cb }
  observe() {
    // Trigger callback immediately with a reasonable default size
    this._cb?.([{ contentRect: { height: 400, width: 600 } }])
  }
  unobserve() {}
  disconnect() {}
}
globalThis.ResizeObserver = MockResizeObserver
window.ResizeObserver = MockResizeObserver
