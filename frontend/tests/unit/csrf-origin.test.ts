import { describe, expect, it } from "vitest"
import { isTrustedOrigin } from "@/lib/auth/origin"

describe("isTrustedOrigin", () => {
  it("accepts the app origin and requests without an Origin header", () => {
    expect(isTrustedOrigin("http://localhost:3000")).toBe(true)
    expect(isTrustedOrigin(null)).toBe(true)
  })

  it("accepts plain localhost in development, compared by hostname", () => {
    expect(isTrustedOrigin("http://127.0.0.1:3001")).toBe(true)
    expect(isTrustedOrigin("http://localhost:5173")).toBe(true)
  })

  it("rejects look-alike and foreign origins", () => {
    expect(isTrustedOrigin("http://localhost.evil.example")).toBe(false)
    expect(isTrustedOrigin("https://evil.example/?localhost")).toBe(false)
    expect(isTrustedOrigin("https://127.0.0.1.evil.example")).toBe(false)
    expect(isTrustedOrigin("not a url")).toBe(false)
  })
})
