import { describe, it, expect } from "vitest"
import { parseSnippet } from "@/components/render-snippet"

describe("Snippet parsing", () => {
  it("returns empty array for empty string", () => {
    expect(parseSnippet("")).toEqual([])
  })

  it("handles text without matches", () => {
    const parts = parseSnippet("Simple plain text without highlights")
    expect(parts).toEqual([
      { text: "Simple plain text without highlights", isMatch: false },
    ])
  })

  it("handles single matched phrase surrounded by « »", () => {
    const parts = parseSnippet("Total amount is «$1,420.00» USD")
    expect(parts).toEqual([
      { text: "Total amount is ", isMatch: false },
      { text: "$1,420.00", isMatch: true },
      { text: " USD", isMatch: false },
    ])
  })

  it("handles multiple matched phrases correctly", () => {
    const parts = parseSnippet("«Invoice» 123 from «Acme Corp»")
    expect(parts).toEqual([
      { text: "Invoice", isMatch: true },
      { text: " 123 from ", isMatch: false },
      { text: "Acme Corp", isMatch: true },
    ])
  })

  it("does not execute HTML tags injected inside snippets", () => {
    const parts = parseSnippet("Look at «<script>alert(1)</script>» safely")
    expect(parts[1]).toEqual({
      text: "<script>alert(1)</script>",
      isMatch: true,
    })
  })
})

