import '@testing-library/jest-dom'
import { resetAppHistoryStack } from './utils/appHistory'

// jsdom doesn't implement layout APIs; mock them
window.HTMLElement.prototype.scrollIntoView = () => {}
window.requestAnimationFrame = (callback) => window.setTimeout(callback, 0)

beforeEach(() => {
  resetAppHistoryStack()
  window.history.replaceState(null, '', '/')
})
