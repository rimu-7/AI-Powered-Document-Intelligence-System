import React from "react"
import { describe, it, expect, vi } from "vitest"
import { screen, fireEvent } from "@testing-library/react"
import { renderWithProviders } from "../utils"
import { EmptyState } from "@/components/empty-state"
import { ErrorState } from "@/components/error-state"

describe("EmptyState component", () => {
  it("renders title, description and calls onAction when button clicked", () => {
    const handleAction = vi.fn()
    renderWithProviders(
      <EmptyState
        title="No invoices found"
        description="Try adjusting your filters"
        actionLabel="Reset filters"
        onAction={handleAction}
      />
    )

    expect(screen.getByText("No invoices found")).toBeInTheDocument()
    expect(screen.getByText("Try adjusting your filters")).toBeInTheDocument()
    const button = screen.getByRole("button", { name: "Reset filters" })
    fireEvent.click(button)
    expect(handleAction).toHaveBeenCalledTimes(1)
  })
})

describe("ErrorState component", () => {
  it("renders error message, request ID and calls onRetry", () => {
    const handleRetry = vi.fn()
    renderWithProviders(
      <ErrorState
        message="Backend service timed out"
        requestId="req-xyz-789"
        onRetry={handleRetry}
      />
    )

    expect(screen.getByText("Something went wrong")).toBeInTheDocument()
    expect(screen.getByText("Backend service timed out")).toBeInTheDocument()
    expect(screen.getByText(/req-xyz-789/)).toBeInTheDocument()

    const retryBtn = screen.getByRole("button", { name: /Retry/i })
    fireEvent.click(retryBtn)
    expect(handleRetry).toHaveBeenCalledTimes(1)
  })
})
