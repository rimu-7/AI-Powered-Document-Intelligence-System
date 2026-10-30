import { describe, it, expect, vi } from "vitest"
import { requestTokenRefresh } from "@/lib/auth/refresh-lock"

describe("Token Refresh Single Flight", () => {
  it("deduplicates concurrent refresh invocations into a single call", async () => {
    let callCount = 0
    const mockRefresh = vi.fn(async () => {
      callCount++
      await new Promise((resolve) => setTimeout(resolve, 50))
      return { ok: true }
    })

    // Simulate 4 concurrent requests triggering refresh at the same time
    const [res1, res2, res3, res4] = await Promise.all([
      requestTokenRefresh(mockRefresh),
      requestTokenRefresh(mockRefresh),
      requestTokenRefresh(mockRefresh),
      requestTokenRefresh(mockRefresh),
    ])

    expect(callCount).toBe(1)
    expect(res1.ok).toBe(true)
    expect(res2.ok).toBe(true)
    expect(res3.ok).toBe(true)
    expect(res4.ok).toBe(true)
  })
})
