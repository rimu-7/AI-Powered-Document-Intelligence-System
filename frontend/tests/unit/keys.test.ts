import { describe, it, expect } from "vitest"
import { qk } from "@/lib/api/keys"

describe("Query Keys Factory", () => {
  it("produces deterministic document query keys", () => {
    const listKey1 = qk.documents.list({ status: "PROCESSED" })
    const listKey2 = qk.documents.list({ status: "PROCESSED" })
    expect(listKey1).toEqual(listKey2)
    expect(qk.documents.detail("doc-123")).toEqual([
      "documents",
      "detail",
      "doc-123",
    ])
  })

  it("produces hierarchical invoice keys", () => {
    expect(qk.invoices.detail("inv-1")).toEqual(["invoices", "detail", "inv-1"])
    expect(qk.invoices.lineItems("inv-1")).toEqual([
      "invoices",
      "inv-1",
      "line-items",
    ])
    expect(qk.invoices.history("inv-1")).toEqual([
      "invoices",
      "inv-1",
      "history",
    ])
  })

  it("produces review queue and search keys", () => {
    expect(qk.reviews.queue({ unassigned: true })).toEqual([
      "reviews",
      "queue",
      { unassigned: true },
    ])
    expect(qk.search.keyword({ query: "office", limit: 20 })).toEqual([
      "search",
      "keyword",
      { query: "office", limit: 20 },
    ])
  })
})
