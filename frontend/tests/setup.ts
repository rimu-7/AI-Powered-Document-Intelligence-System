import "@testing-library/jest-dom/vitest"
import { beforeAll, afterEach, afterAll } from "vitest"
import { server } from "./msw/server"

if (typeof window !== "undefined") {
  class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
  window.ResizeObserver = ResizeObserver
  global.ResizeObserver = ResizeObserver
  window.HTMLElement.prototype.scrollIntoView = () => {}
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: "warn" })
})

afterEach(() => {
  server.resetHandlers()
})

afterAll(() => {
  server.close()
})
