import { describe, it, expect } from "vitest"
import { formatMoney, formatBytes, formatDate } from "@/lib/format"

describe("Format Utilities", () => {
  describe("formatMoney", () => {
    it("formats standard amounts without converting to float arithmetic", () => {
      const res = formatMoney("1234.50", "USD")
      expect(res).toContain("1,234.50")
    })

    it("handles null or empty values gracefully", () => {
      expect(formatMoney(null, null)).toBe("—")
      expect(formatMoney("", null)).toBe("—")
      expect(formatMoney(undefined, null)).toBe("—")
    })

    it("formats with null currency as decimal and never produces EUR", () => {
      const res = formatMoney("15724.91", null)
      expect(res).toBe("15,724.91")
      expect(res).not.toContain("€")
      expect(res).not.toContain("EUR")

      const resWithSymbol = formatMoney("15724.91", null, "$")
      expect(resWithSymbol).toBe("$15,724.91")
      expect(resWithSymbol).not.toContain("€")
    })

    it("respects minor units from config or default currency mapping", () => {
      const jpy = formatMoney("1234", "JPY")
      expect(jpy).not.toContain(".00")

      const bhd = formatMoney("12.345", "BHD", undefined, 3)
      expect(bhd).toContain("12.345")
    })
  })

  describe("formatBytes", () => {
    it("formats zero bytes", () => {
      expect(formatBytes(0)).toBe("0 B")
    })

    it("formats megabytes and gigabytes properly", () => {
      expect(formatBytes(1024)).toBe("1 KB")
      expect(formatBytes(1024 * 1024)).toBe("1 MB")
      expect(formatBytes(2.5 * 1024 * 1024 * 1024)).toBe("2.5 GB")
    })
  })

  describe("formatDate", () => {
    it("formats valid ISO timestamp", () => {
      const formatted = formatDate("2026-10-29T10:00:00Z", "yyyy-MM-dd")
      expect(formatted).toBe("2026-10-29")
    })

    it("returns dash for falsy dates", () => {
      expect(formatDate(null)).toBe("—")
      expect(formatDate(undefined)).toBe("—")
    })
  })
})
