import '@testing-library/jest-dom/vitest'
import { vi } from 'vitest'

// jsdom's origin is http://localhost:3000, which the app treats as loopback, so a
// component that probes the control plane makes a REAL request during tests. If
// anything happens to listen on that port the suite reads whatever it serves, so
// results depend on the developer's machine. Refuse the network by default; tests
// that want an API stub fetch themselves.
globalThis.fetch = (async (input: RequestInfo | URL) => {
  throw new Error(`unstubbed network call in tests: ${String(input)}`)
}) as typeof fetch

// jsdom has no matchMedia; motion/react's useReducedMotion needs it.
if (typeof window !== 'undefined' && !window.matchMedia) {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    addListener: vi.fn(),
    removeListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia
}

// jsdom lacks ResizeObserver (cmdk) and scrollIntoView (cmdk active-item).
if (typeof window !== 'undefined' && !window.ResizeObserver) {
  window.ResizeObserver = class {
    observe() {}
    unobserve() {}
    disconnect() {}
  } as unknown as typeof window.ResizeObserver
}
if (typeof window !== 'undefined' && !window.HTMLElement.prototype.scrollIntoView) {
  window.HTMLElement.prototype.scrollIntoView = vi.fn()
}
