import '@testing-library/jest-dom/vitest'

// jsdom does not implement scrolling; the virtualized review table calls it
window.scrollTo = () => {}
