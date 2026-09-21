import '@testing-library/jest-dom'
import { afterEach } from 'vitest'

// jsdom doesn't implement layout APIs; mock them
window.HTMLElement.prototype.scrollIntoView = () => {}
window.requestAnimationFrame = (callback) => window.setTimeout(callback, 0)

// The app is routed now, so a test that clicks its way to /lesson/x leaves the
// shared jsdom window sitting there — and the next `render(<App />)` in the same
// file would mount on that URL instead of the learning map it assumes. Every test
// therefore starts from a known address; nothing else resets history.
afterEach(() => {
  window.history.replaceState(null, '', '/')
})
