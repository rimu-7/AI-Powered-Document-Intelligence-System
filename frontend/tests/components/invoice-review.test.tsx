import React from "react"
import { describe, it, expect, vi } from "vitest"
import { screen, fireEvent } from "@testing-library/react"
import { renderWithProviders } from "../utils"
import InvoiceReviewPage from "@/app/(app)/invoices/[id]/page"

vi.mock("next/navigation", () => ({
  useRouter: () => ({
    push: vi.fn(),
    back: vi.fn(),
  }),
}))

describe("InvoiceReviewPage component", () => {
  it("renders invoice workspace details from MSW", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)

    // Wait for invoice number and supplier name to load
    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()
    expect(screen.getByText("Acme Supplies Inc.")).toBeInTheDocument()
    expect(screen.getByText("USD 1100.00")).toBeInTheDocument()
    expect(screen.getByText(/Line Items \(1\)/i)).toBeInTheDocument()
  })

  it("handles edit mode toggle and form fields", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)

    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()

    // Click Edit button
    const editButton = screen.getByRole("button", { name: /Edit/i })
    fireEvent.click(editButton)

    // Expect Cancel and Save changes buttons
    expect(screen.getByRole("button", { name: /Cancel/i })).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /Save Changes/i })).toBeInTheDocument()
  })

  it("opens approve dialog and displays blocking validation issues warning", async () => {
    renderWithProviders(<InvoiceReviewPage params={{ id: "inv-001" }} />)

    expect(await screen.findByText("Invoice: INV-2026-001")).toBeInTheDocument()

    // Click Approve button in header
    const approveBtn = screen.getByRole("button", { name: /Approve/i })
    fireEvent.click(approveBtn)

    // Approve Dialog should open
    expect(await screen.findByText("Approve Invoice")).toBeInTheDocument()
    // It should warn about blocking validation issues
    expect(screen.getByText(/Open Blocking Issues \(1\)/i)).toBeInTheDocument()
    expect(
      screen.getByText(/I acknowledge these issues and wish to approve anyway/i)
    ).toBeInTheDocument()
  })
})
