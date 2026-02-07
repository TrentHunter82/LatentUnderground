import '@testing-library/jest-dom'

// JSDOM doesn't implement scrollIntoView
Element.prototype.scrollIntoView = () => {}
