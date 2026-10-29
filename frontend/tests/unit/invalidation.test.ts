import { describe, it, expect, vi } from "vitest"
import { QueryClient } from "@tanstack/react-query"
import { invalidateForMutation } from "@/lib/api/invalidation"
import { qk } from "@/lib/api/keys"

describe("invalidation map", () => {
  it("invalidates document list, jobs, and admin stats on upload_documents", async () => {
    const queryClient = new QueryClient()
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries")

    await invalidateForMutation(queryClient, "upload_documents")

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.documents.all() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.jobs.all() })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.admin.stats() })
  })

  it("invalidates invoice detail, document, reviews on correct_invoice", async () => {
    const queryClient = new QueryClient()
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries")

    await invalidateForMutation(queryClient, "correct_invoice", {
      invoiceId: "inv-123",
      documentId: "doc-456",
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.invoices.detail("inv-123") })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.invoices.history("inv-123") })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.documents.invoices("doc-456") })
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.reviews.all() })
  })

  it("invalidates user list and sessions on revoke_user_sessions", async () => {
    const queryClient = new QueryClient()
    const invalidateSpy = vi.spyOn(queryClient, "invalidateQueries")

    await invalidateForMutation(queryClient, "revoke_user_sessions", {
      userId: "usr-999",
    })

    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: qk.admin.users() })
  })
})

