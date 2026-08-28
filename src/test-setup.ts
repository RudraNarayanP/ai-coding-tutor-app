import '@testing-library/jest-dom'

// jsdom doesn't implement layout APIs; mock them
window.HTMLElement.prototype.scrollIntoView = () => {}
window.requestAnimationFrame = (callback) => window.setTimeout(callback, 0)
